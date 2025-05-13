import os
import json
import yaml
import boto3
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from botocore.exceptions import ClientError
import logging
from agent_registry import BaseA2AAgent, register_agent

logger = logging.getLogger(__name__)

@register_agent('aws_account_analysis-a2a')
class AWSAccountAnalysisAgent(BaseA2AAgent):
    """
    A2A Agent that inspects AWS IAM Role trust policies and S3 bucket policies
    to identify external accounts (known vendors, unknown accounts, trusted entities)
    and checks for missing ExternalId conditions.
    """
    # Reference URL for known AWS accounts
    KNOWN_ACCOUNTS_URL = (
        "https://raw.githubusercontent.com/fwdcloudsec/known_aws_accounts/main/accounts.yaml"
    )

    async def analyze(self, agent_id: str, skill_id: str, parameters: Dict[str, Any], 
                     request_context: Dict[str, Any], task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute external-access analysis and return structured findings."""
        logger.info(f"Starting AWS Known External Access analysis with parameters: {parameters}")
        
        try:
            # Get AWS credentials from parameters
            aws_access_key = parameters.get('AWS Access Key')
            aws_secret_key = parameters.get('AWS Secret Key')
            
            # Check if credentials are in encrypted format (dict with 'is_encrypted' and 'value')
            if isinstance(aws_access_key, dict) and aws_access_key.get('is_encrypted'):
                logger.warning("AWS Access Key is still encrypted. Credentials were not properly decrypted by the A2A client.")
                return {
                    "status": "error",
                    "error_message": "AWS credentials are encrypted. The A2A client failed to decrypt them. ",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            if isinstance(aws_secret_key, dict) and aws_secret_key.get('is_encrypted'):
                logger.warning("AWS Secret Key is still encrypted. Credentials were not properly decrypted by the A2A client.")
                return {
                    "status": "error",
                    "error_message": "AWS credentials are encrypted. The A2A client failed to decrypt them.",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Require explicit credentials - no profile or default credentials
            if not aws_access_key or not aws_secret_key:
                logger.error("Missing required AWS credentials")
                return {
                    "status": "error",
                    "error_message": "Missing required AWS credentials. This SaaS agent requires explicit AWS Access Key and AWS Secret Key to be provided.",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Initialize session with provided credentials only
            logger.info("Using provided AWS credentials")
            session = boto3.Session(
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key
            )
            
            # Use session directly in all boto3 calls
            sts = session.client('sts')
            iam = session.client('iam')
            
            # 1. Gather reference and context
            known = self.fetch_reference_data()
            trusted_file = parameters.get('trusted_accounts_file', 'trusted_accounts.yaml')
            trusted = self.fetch_trusted_accounts(trusted_file)
            aliases = self.get_account_aliases(session)

            # 2. Analyze IAM roles and S3 buckets
            iam_results = self.check_iam_roles(session, known, trusted, aliases)
            s3_results = self.check_s3_buckets(session, known, trusted, aliases)

            # 3. Properly merge results
            merged_results = {
                'iam': iam_results,
                's3': s3_results,
                'summary': 'AWS external access analysis complete',
                'timestamp': datetime.utcnow().isoformat(),
                
                # Merged data for backward compatibility
                'known_vendors': self._merge_dicts(iam_results.get('known_vendors', {}), 
                                                 s3_results.get('known_vendors', {})),
                'unknown_accounts': self._merge_dicts(iam_results.get('unknown_accounts', {}), 
                                                    s3_results.get('unknown_accounts', {})),
                'trusted_entities': self._merge_dicts(iam_results.get('trusted_entities', {}), 
                                                    s3_results.get('trusted_entities', {})),
                'vulnerable_roles': iam_results.get('vulnerable_roles', {}),
                'cross_account_roles': iam_results.get('cross_account_roles', {})
            }
            
            # Add cross-account metrics
            merged_results['metrics'] = {
                'known_vendors_count': len(merged_results['known_vendors']),
                'unknown_accounts_count': len(merged_results['unknown_accounts']),
                'trusted_entities_count': len(merged_results['trusted_entities']),
                'vulnerable_roles_count': len(merged_results['vulnerable_roles']),
                'cross_account_roles_count': len(merged_results['cross_account_roles']),
                'total_cross_account_roles': sum(len(roles) for roles in merged_results['cross_account_roles'].values())
            }
            
            logger.info("AWS Known External Access analysis completed successfully")
            return merged_results
        except Exception as e:
            logger.error(f"Error performing AWS Known External Access analysis: {str(e)}")
            return {
                "status": "error",
                "error_message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def fetch_reference_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch list of known AWS accounts from upstream GitHub repository.
        Returns mapping account_id -> vendor metadata.
        """
        try:
            resp = requests.get(self.KNOWN_ACCOUNTS_URL, timeout=10)
            resp.raise_for_status()
            vendors = yaml.safe_load(resp.text) or []
            mapping: Dict[str, Dict[str, Any]] = {}
            for v in vendors:
                for acct in v.get('accounts', []):
                    mapping[str(acct)] = {
                        'name': v.get('name', 'Unknown'),
                        'type': v.get('type', 'third-party'),
                        'source': v.get('source', [])
                    }
            return mapping
        except Exception as e:
            logger.error(f"Error fetching reference data: {str(e)}")
            return {}

    def fetch_trusted_accounts(self, path: str) -> Dict[str, Dict[str, Any]]:
        """
        Load locally defined trusted accounts from YAML file.
        config_data may specify custom path.
        """
        if not os.path.exists(path):
            logger.warning(f"Trusted accounts file not found: {path}")
            return {}
        try:
            data = yaml.safe_load(open(path)) or []
            mapping: Dict[str, Dict[str, Any]] = {}
            for ent in data:
                for acct in ent.get('accounts', []):
                    mapping[str(acct)] = {
                        'name': ent.get('name', 'Internal'),
                        'type': 'trusted',
                        'description': ent.get('description', '')
                    }
            return mapping
        except Exception as e:
            logger.error(f"Error loading trusted accounts: {str(e)}")
            return {}

    def get_account_aliases(self, session) -> Dict[str, str]:
        """
        Retrieve AWS account ID alias for the current caller.
        """
        aliases: Dict[str, str] = {}
        try:
            sts = session.client('sts')
            iam = session.client('iam')
            acct = sts.get_caller_identity()['Account']
            # default alias to account ID
            aliases[acct] = acct
            resp = iam.list_account_aliases()
            if resp.get('AccountAliases'):
                aliases[acct] = resp['AccountAliases'][0]
        except Exception as e:
            logger.error(f"Error getting account aliases: {str(e)}")
        return aliases

    def extract_account_ids(self, doc: Any) -> List[str]:
        """
        Recursively extract 12-digit AWS account IDs from policy document.
        """
        found = set()
        def recurse(node: Any):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k == "AWS":
                        if isinstance(v, str) and "arn:aws" in v:
                            # Extract account ID from ARN
                            parts = v.split(":")
                            if len(parts) >= 5 and parts[4].isdigit() and len(parts[4]) == 12:
                                found.add(parts[4])
                        elif isinstance(v, str) and v.isdigit() and len(v) == 12:
                            found.add(v)
                        elif isinstance(v, list):
                            for item in v:
                                if isinstance(item, str) and "arn:aws" in item:
                                    parts = item.split(":")
                                    if len(parts) >= 5 and parts[4].isdigit() and len(parts[4]) == 12:
                                        found.add(parts[4])
                                elif isinstance(item, str) and item.isdigit() and len(item) == 12:
                                    found.add(item)
                    else:
                        recurse(v)
            elif isinstance(node, list):
                for i in node:
                    recurse(i)
        
        recurse(doc)
        return list(found)

    def has_external_id(self, policy: Dict[str, Any]) -> bool:
        """
        Checks trust policy for sts:ExternalId condition.
        """
        stmts = policy.get('Statement')
        if not stmts:
            return False
        stmts = stmts if isinstance(stmts, list) else [stmts]
        for s in stmts:
            if s.get('Effect') != 'Allow':
                continue
            cond = s.get('Condition', {})
            for _, vals in cond.items():
                if isinstance(vals, dict) and 'sts:ExternalId' in vals:
                    return True
        return False

    def check_iam_roles(self,
                        session,
                        known: Dict[str, Any],
                        trusted: Dict[str, Any],
                        aliases: Dict[str, str]
                        ) -> Dict[str, Any]:
        """
        Check IAM roles for external access.
        """
        logger.info("Checking IAM roles for external access")
        iam = session.client('iam')
        sts = session.client('sts')
        # Get current account ID
        current_account = sts.get_caller_identity()['Account']
        
        paginator = iam.get_paginator('list_roles')
        res = {
            'known_vendors': {}, 'unknown_accounts': {},
            'trusted_entities': {}, 'vulnerable_roles': {},
            'cross_account_roles': {}  # New category for cross-account roles
        }
        for page in paginator.paginate():
            for role in page.get('Roles', []):
                name = role['RoleName']
                policy = role.get('AssumeRolePolicyDocument', {})
                acct_ids = self.extract_account_ids(policy)
                
                # Mark any role that allows access from a different account
                cross_account_access = [acct for acct in acct_ids if acct != current_account]
                if cross_account_access:
                    for acct in cross_account_access:
                        acct_display = acct
                        if acct in known:
                            acct_display = f"{acct} ({known[acct]['name']})"
                        elif acct in trusted:
                            acct_display = f"{acct} ({trusted[acct]['name']})"
                        else:
                            acct_display = f"{acct} ({aliases.get(acct, 'Unknown')})"
                            
                        res['cross_account_roles'].setdefault(acct_display, []).append(name)
                
                # Continue with existing categorization
                for acct in acct_ids:
                    if acct in trusted:
                        res['trusted_entities'].setdefault(trusted[acct]['name'], []).append(name)
                    elif acct in known:
                        vendor = known[acct]['name']
                        res['known_vendors'].setdefault(vendor, []).append(name)
                        if not self.has_external_id(policy):
                            res['vulnerable_roles'].setdefault(vendor, []).append(name)
                    else:
                        display = f"{acct} ({aliases.get(acct, acct)})"
                        res['unknown_accounts'].setdefault(display, []).append(name)
                        if not self.has_external_id(policy):
                            res['vulnerable_roles'].setdefault(display, []).append(name)
        return res

    def check_s3_buckets(self,
                         session,
                         known: Dict[str, Any],
                         trusted: Dict[str, Any],
                         aliases: Dict[str, str]
                         ) -> Dict[str, Any]:
        """
        Check S3 buckets for external access.
        """
        logger.info("Checking S3 buckets for external access")
        s3 = session.client('s3')
        res = {'known_vendors': {}, 'unknown_accounts': {}, 'trusted_entities': {}}
        try:
            for b in s3.list_buckets().get('Buckets', []):
                name = b['Name']
                try:
                    doc = json.loads(s3.get_bucket_policy(Bucket=name)['Policy'])
                except ClientError:
                    continue
                acct_ids = self.extract_account_ids(doc)
                for acct in acct_ids:
                    if acct in trusted:
                        res['trusted_entities'].setdefault(trusted[acct]['name'], []).append(name)
                    elif acct in known:
                        vendor = known[acct]['name']
                        res['known_vendors'].setdefault(vendor, []).append(name)
                    else:
                        display = f"{acct} ({aliases.get(acct, acct)})"
                        res['unknown_accounts'].setdefault(display, []).append(name)
        except Exception as e:
            logger.error(f"Error checking S3 buckets: {str(e)}")
        return res

    def _merge_dicts(self, dict1: Dict[str, list], dict2: Dict[str, list]) -> Dict[str, list]:
        """Merge two dictionaries of lists, combining lists for the same keys."""
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result:
                # Combine lists and remove duplicates
                result[key] = list(set(result[key] + value))
            else:
                result[key] = value
        return result 