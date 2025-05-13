import os
import boto3
import botocore
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from agent_registry import BaseA2AAgent, register_agent

# Configure logging
logger = logging.getLogger(__name__)

# Stub for vendor lookup; extend or replace as needed
class VendorMap:
    def __init__(self, mapping: Dict[str, str] = None):
        self.account_to_name = mapping or {}
    def get_vendor_name(self, account_id: str) -> str:
        return self.account_to_name.get(account_id, "")

@register_agent('aws_ec2_eye-a2a')
class AWSEc2EyeAgent(BaseA2AAgent):
    """
    A2A Agent for EC2 AMI inventory, EBS snapshot lineage, and categorization.
    Classifies AMIs by provider and trust, replicating aws_ec2_eye script logic,
    and checks backing snapshots for public-sharing permissions.
    """
    async def analyze(self, agent_id: str, skill_id: str, parameters: Dict[str, Any], 
                     request_context: Dict[str, Any], task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute EC2 AMI analysis and return structured findings.
        """
        logger.info(f"Starting AWS EC2 Eye analysis with parameters: {parameters}")
        
        try:
            # 1. Parse configuration
            regions = parameters.get('regions', [])  # list of region strings
            trusted_list = parameters.get('trusted_accounts', [])  # list of account IDs

            # Get AWS credentials - they should already be decrypted by the A2A client
            aws_access_key = parameters.get('AWS Access Key')
            aws_secret_key = parameters.get('AWS Secret Key')
            
            # Check if credentials are in encrypted format (dict with 'is_encrypted' and 'value')
            if isinstance(aws_access_key, dict) and aws_access_key.get('is_encrypted'):
                logger.warning("AWS Access Key is still encrypted. Credentials were not properly decrypted by the A2A client.")
                return {
                    "status": "error",
                    "error_message": "AWS credentials are encrypted. The A2A client failed to decrypt them. Make sure the ENCRYPTION_MASTER_KEY environment variable is set in the backend environment.",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            if isinstance(aws_secret_key, dict) and aws_secret_key.get('is_encrypted'):
                logger.warning("AWS Secret Key is still encrypted. Credentials were not properly decrypted by the A2A client.")
                return {
                    "status": "error",
                    "error_message": "AWS credentials are encrypted. The A2A client failed to decrypt them. Make sure the ENCRYPTION_MASTER_KEY environment variable is set in the backend environment.",
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
                
            sts = session.client('sts', region_name='us-east-1')
            ec2_global = session.client('ec2', region_name='us-east-1')

            # 2. Determine caller ID
            caller = sts.get_caller_identity()['Account']

            # 3. Regions to scan
            if not regions:
                regions = [r['RegionName'] for r in ec2_global.describe_regions()['Regions']]

            # 4. Data structures
            ami_to_instances     = defaultdict(list)
            processed_amis       = set()
            verified             = {}
            selfhosted           = {}
            allowed              = {}
            trusted              = {}
            private_shared       = {}
            known_unverified     = {}
            unknown_unverified   = {}
            snapshot_lineage     = {}  # Map AMI -> list of snapshot info
            total_instances      = 0
            
            # 5. Build VendorMap stub
            vendor_map = VendorMap()  # extend mapping via parameters if provided

            # 6. Scan each region
            for reg in regions:
                ec2 = session.client('ec2', region_name=reg)
                # a. List instances
                paginator = ec2.get_paginator('describe_instances')
                instances = []
                for page in paginator.paginate():
                    for res in page.get('Reservations', []):
                        for inst in res.get('Instances', []):
                            instances.append(inst)
                if not instances:
                    continue
                total_instances += len(instances)
                # b. Map AMI to instances
                for inst in instances:
                    ami = inst.get('ImageId')
                    name = next((t['Value'] for t in inst.get('Tags', []) if t['Key']=='Name'), '')
                    ami_to_instances[ami].append({'InstanceId': inst['InstanceId'], 'Name': name, 'Region': reg})
                # c. Fetch allowed AMIs state
                try:
                    resp = ec2.get_allowed_images_settings()
                    allowed_state    = resp.get('State')
                    allowed_accounts = [p for c in resp.get('ImageCriteria', []) for p in c.get('ImageProviders', [])]
                except botocore.exceptions.ClientError:
                    allowed_state, allowed_accounts = None, []
                # d. Classify each AMI once
                for ami, inst_list in ami_to_instances.items():
                    if ami in processed_amis:
                        continue
                    processed_amis.add(ami)

                    # retrieve image metadata
                    try:
                        imgs = ec2.describe_images(ImageIds=[ami]).get('Images', [])
                        img  = imgs[0] if imgs else {}
                    except botocore.exceptions.ClientError:
                        img = {}

                    public = img.get('Public', False)
                    owner  = img.get('OwnerId', '')
                    alias  = img.get('ImageOwnerAlias', '')
                    vendor = vendor_map.get_vendor_name(owner) or 'Unknown'
                    data   = {'alias': alias, 'owner': owner, 'public': public, 'vendor': vendor, 'region': reg}

                    # classification logic
                    if alias in ('amazon', 'aws-marketplace'):
                        verified[ami] = data
                    elif alias == 'self' or owner == caller:
                        selfhosted[ami] = data
                    elif allowed_state in ('enabled', 'audit-mode') and owner in allowed_accounts:
                        allowed[ami] = data
                    elif owner in trusted_list:
                        trusted[ami] = data
                    elif not public:
                        private_shared[ami] = data
                    elif vendor != 'Unknown':
                        known_unverified[ami] = data
                    else:
                        unknown_unverified[ami] = data

                    # --- Snapshot Lineage for private/shared AMIs ---
                    if ami in private_shared or ami in allowed or ami in trusted:
                        snaps_info: List[Dict[str, Any]] = []
                        for bd in img.get('BlockDeviceMappings', []):
                            ebs = bd.get('Ebs')
                            if not ebs:
                                continue
                            snap_id = ebs.get('SnapshotId')
                            if not snap_id:
                                continue
                            # Check snapshot permissions
                            try:
                                attr = ec2.describe_snapshot_attribute(SnapshotId=snap_id, Attribute='createVolumePermission')
                                perms = attr.get('CreateVolumePermissions', [])
                                public_snap = any(p.get('Group') == 'all' for p in perms)
                                shared_with = [p.get('UserId') for p in perms if 'UserId' in p]
                            except botocore.exceptions.ClientError:
                                public_snap = False
                                shared_with = []
                            snaps_info.append({'snapshot_id': snap_id, 'public': public_snap, 'shared_with': shared_with})
                        if snaps_info:
                            snapshot_lineage[ami] = snaps_info

            # 7. Compile results
            results = {
                'summary': 'EC2 AMI inventory and EBS snapshot analysis complete',
                'timestamp': datetime.utcnow().isoformat(),
                'total_instances': total_instances,
                'total_amis': len(processed_amis),

                # AMI categorizations
                'ami_data': {
                    'verified': verified,
                    'selfhosted': selfhosted,
                    'allowed': allowed,
                    'trusted': trusted,
                    'private_shared': private_shared,
                    'known_unverified': known_unverified,
                    'unknown_unverified': unknown_unverified,
                },
                # EBS snapshot lineage for key AMIs
                'snapshot_lineage': snapshot_lineage,

                # Aggregated counts
                'metrics': {
                    'verified_AMIs_count': len(verified),
                    'selfhosted_AMIs_count': len(selfhosted),
                    'allowed_AMIs_count': len(allowed),
                    'trusted_AMIs_count': len(trusted),
                    'private_shared_AMIs_count': len(private_shared),
                    'known_AMIs_count': len(known_unverified),
                    'unknown_AMIs_count': len(unknown_unverified),
                    'AMIs_with_snapshot_lineage': len(snapshot_lineage),
                    'total_instances': total_instances,
                    'total_amis': len(processed_amis)
                }
            }
            
            logger.info("AWS EC2 Eye analysis completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Error performing AWS EC2 Eye analysis: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error performing AWS EC2 Eye analysis: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            } 