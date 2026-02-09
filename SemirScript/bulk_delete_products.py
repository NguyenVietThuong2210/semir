"""
Bulk Product Deletion Script with OAuth2 Authentication
========================================================
Handles 80,000+ product deletions with:
- Proper authentication flow
- Rate limiting and retry logic
- Progress tracking and logging
- Error handling and recovery
- Batch processing with checkpoints
"""

import os
import time
import json
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import csv

# ================= CONFIGURATION =================

class Config:
    # SSO Configuration
    SSO_SERVER_URI = "https://id.cnv.vn"
    SSO_CLIENT_ID = "4e399845e7944241927e77e837794f1e"
    SSO_CLIENT_SECRET = "a4ba379b7037426b9fbb0455725c5979"
    SSO_REDIRECT_URI = "http://localhost:5000/callback"
    
    # API Configuration
    API_BASE_URL = "https://apis.cnvloyalty.com"
    PRODUCTS_ENDPOINT = "/products.json"
    DELETE_ENDPOINT = "/products/{id}.json"
    
    # Performance Configuration
    BATCH_SIZE = 100  # Process in batches
    RATE_LIMIT_DELAY = 0.1  # Seconds between requests (10 req/sec)
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # Seconds
    REQUEST_TIMEOUT = 30  # Seconds
    
    # Checkpoint Configuration
    CHECKPOINT_INTERVAL = 500  # Save progress every N deletions
    CHECKPOINT_FILE = "deletion_checkpoint.json"
    
    # Logging Configuration
    LOG_DIR = "logs"
    LOG_FILE = f"deletion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    CSV_LOG_FILE = f"deleted_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


# ================= LOGGING SETUP =================

def setup_logging():
    """Configure comprehensive logging with UTF-8 encoding"""
    # Create logs directory
    Path(Config.LOG_DIR).mkdir(exist_ok=True)
    
    log_path = Path(Config.LOG_DIR) / Config.LOG_FILE
    
    # Fix for Windows: Force UTF-8 encoding
    import sys
    if sys.platform == 'win32':
        # Set console to UTF-8
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    
    # Configure logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()  # Also print to console
        ]
    )
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ================= CSV LOGGER =================

class CSVLogger:
    """Log deleted products to CSV for tracking"""
    
    def __init__(self):
        self.csv_path = Path(Config.LOG_DIR) / Config.CSV_LOG_FILE
        self.fieldnames = [
            'timestamp', 'product_id', 'status', 
            'response_code', 'error_message', 'retry_count'
        ]
        
        # Create CSV with headers
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
    
    def log_deletion(self, product_id: str, status: str, 
                    response_code: int = None, 
                    error_message: str = None,
                    retry_count: int = 0):
        """Log a deletion attempt"""
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'product_id': product_id,
                'status': status,
                'response_code': response_code,
                'error_message': error_message,
                'retry_count': retry_count
            })


# ================= CHECKPOINT MANAGER =================

class CheckpointManager:
    """Manage deletion progress checkpoints for recovery"""
    
    def __init__(self):
        self.checkpoint_path = Path(Config.CHECKPOINT_FILE)
    
    def save_checkpoint(self, deleted_ids: List[str], 
                       failed_ids: List[str],
                       total_processed: int,
                       total_count: int):
        """Save current progress"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'deleted_ids': deleted_ids,
            'failed_ids': failed_ids,
            'total_processed': total_processed,
            'total_count': total_count,
            'completion_percentage': (total_processed / total_count * 100) if total_count > 0 else 0
        }
        
        with open(self.checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        logger.info(f"[SAVE] Checkpoint saved: {total_processed}/{total_count} processed")
    
    def load_checkpoint(self) -> Optional[Dict]:
        """Load last checkpoint if exists"""
        if not self.checkpoint_path.exists():
            return None
        
        try:
            with open(self.checkpoint_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def clear_checkpoint(self):
        """Remove checkpoint file after completion"""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()


# ================= OAUTH2 CLIENT =================

class OAuth2Client:
    """Handle OAuth2 authentication and token management"""
    
    def __init__(self):
        self.access_token = None
        self.token_type = None
        self.expires_at = None
    
    def set_token_manually(self, access_token: str, token_type: str = "TOKEN"):
        """
        Set token manually if you already have it from the Flask app
        
        Usage:
            client = OAuth2Client()
            client.set_token_manually("your_access_token_here")
        """
        self.access_token = access_token
        self.token_type = token_type
        logger.info("[OK] Access token set manually")
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests"""
        if not self.access_token:
            raise ValueError("No access token available. Please authenticate first.")
        
        return {
            "Authorization": f"{self.token_type} {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def verify_token(self) -> bool:
        """Verify if the current token is valid"""
        try:
            response = requests.post(
                f"{Config.SSO_SERVER_URI}/auth/verify",
                headers=self.get_auth_headers(),
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if response.status_code == 200:
                logger.info("[OK] Token verified successfully")
                return True
            else:
                logger.error(f"[FAIL] Token verification failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[FAIL] Token verification error: {e}")
            return False


# ================= PRODUCT DELETION CLIENT =================

class ProductDeletionClient:
    """Handle product fetching and deletion with rate limiting"""
    
    def __init__(self, oauth_client: OAuth2Client):
        self.oauth_client = oauth_client
        self.session = requests.Session()
        self.csv_logger = CSVLogger()
        self.checkpoint_manager = CheckpointManager()
        
        # Statistics
        self.stats = {
            'total_fetched': 0,
            'total_deleted': 0,
            'total_failed': 0,
            'start_time': None,
            'end_time': None
        }
    
    def fetch_all_products(self) -> List[Dict]:
        """
        Fetch all products from API with pagination support
        
        Returns:
            List of product dictionaries with at minimum {'id': ...}
        """
        logger.info("[>>] Fetching all products...")
        all_products = []
        page = 1
        
        while True:
            try:
                logger.info(f"Fetching page {page}...")
                
                response = self.session.get(
                    f"{Config.API_BASE_URL}{Config.PRODUCTS_ENDPOINT}",
                    headers=self.oauth_client.get_auth_headers(),
                    params={'page': page, 'limit': 100},  # Adjust based on API
                    timeout=Config.REQUEST_TIMEOUT
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Handle different response structures
                products = data if isinstance(data, list) else data.get('products', [])
                
                if not products:
                    break
                
                all_products.extend(products)
                logger.info(f"  [+] Fetched {len(products)} products (total: {len(all_products)})")
                
                # Check if there are more pages
                if len(products) < 100:  # No more pages
                    break
                
                page += 1
                time.sleep(Config.RATE_LIMIT_DELAY)
                
            except Exception as e:
                logger.error(f"[X] Error fetching products on page {page}: {e}")
                break
        
        self.stats['total_fetched'] = len(all_products)
        logger.info(f"[OK] Total products fetched: {len(all_products)}")
        
        return all_products
    
    def delete_product(self, product_id: str, retry_count: int = 0) -> bool:
        """
        Delete a single product with retry logic
        
        Args:
            product_id: Product ID to delete
            retry_count: Current retry attempt number
            
        Returns:
            True if deletion successful, False otherwise
        """
        url = f"{Config.API_BASE_URL}{Config.DELETE_ENDPOINT.format(id=product_id)}"
        
        try:
            response = self.session.delete(
                url,
                headers=self.oauth_client.get_auth_headers(),
                timeout=Config.REQUEST_TIMEOUT
            )
            
            # Consider 200, 204, and 404 (already deleted) as success
            if response.status_code in [200, 204, 404]:
                self.csv_logger.log_deletion(
                    product_id=product_id,
                    status='success',
                    response_code=response.status_code,
                    retry_count=retry_count
                )
                return True
            
            # Handle rate limiting (429)
            elif response.status_code == 429:
                if retry_count < Config.MAX_RETRIES:
                    wait_time = Config.RETRY_DELAY * (retry_count + 1)
                    logger.warning(f"[WAIT] Rate limited for product {product_id}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    return self.delete_product(product_id, retry_count + 1)
                else:
                    logger.error(f"[X] Max retries reached for product {product_id}")
                    self.csv_logger.log_deletion(
                        product_id=product_id,
                        status='failed',
                        response_code=response.status_code,
                        error_message='Rate limit - max retries exceeded',
                        retry_count=retry_count
                    )
                    return False
            
            # Other errors
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"[X] Failed to delete product {product_id}: {error_msg}")
                
                if retry_count < Config.MAX_RETRIES:
                    time.sleep(Config.RETRY_DELAY)
                    return self.delete_product(product_id, retry_count + 1)
                
                self.csv_logger.log_deletion(
                    product_id=product_id,
                    status='failed',
                    response_code=response.status_code,
                    error_message=error_msg,
                    retry_count=retry_count
                )
                return False
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[X] Exception deleting product {product_id}: {error_msg}")
            
            if retry_count < Config.MAX_RETRIES:
                time.sleep(Config.RETRY_DELAY)
                return self.delete_product(product_id, retry_count + 1)
            
            self.csv_logger.log_deletion(
                product_id=product_id,
                status='failed',
                error_message=error_msg,
                retry_count=retry_count
            )
            return False
    
    def bulk_delete(self, product_ids: List[str], resume: bool = True):
        """
        Delete products in bulk with progress tracking
        
        Args:
            product_ids: List of product IDs to delete
            resume: Whether to resume from checkpoint if exists
        """
        deleted_ids = []
        failed_ids = []
        
        # Try to resume from checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint() if resume else None
        
        if checkpoint:
            logger.info("[>>] Resuming from checkpoint...")
            deleted_ids = checkpoint.get('deleted_ids', [])
            failed_ids = checkpoint.get('failed_ids', [])
            
            # Filter out already processed IDs
            remaining_ids = [pid for pid in product_ids if pid not in deleted_ids and pid not in failed_ids]
            logger.info(f"  [+] Already processed: {len(deleted_ids) + len(failed_ids)}")
            logger.info(f"  [+] Remaining: {len(remaining_ids)}")
        else:
            remaining_ids = product_ids
        
        total_count = len(product_ids)
        self.stats['start_time'] = datetime.now()
        
        logger.info(f"[DEL] Starting bulk deletion of {len(remaining_ids)} products...")
        logger.info(f"[CFG] Rate limit: {1/Config.RATE_LIMIT_DELAY:.0f} req/sec")
        logger.info(f"[CFG] Batch size: {Config.BATCH_SIZE}")
        
        # Process in batches
        for i, product_id in enumerate(remaining_ids, 1):
            # Delete product
            success = self.delete_product(product_id)
            
            if success:
                deleted_ids.append(product_id)
                self.stats['total_deleted'] += 1
            else:
                failed_ids.append(product_id)
                self.stats['total_failed'] += 1
            
            # Progress logging
            total_processed = len(deleted_ids) + len(failed_ids)
            if i % 50 == 0 or i == len(remaining_ids):
                elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                rate = total_processed / elapsed if elapsed > 0 else 0
                remaining = len(remaining_ids) - i
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                
                logger.info(
                    f"[STAT] Progress: {total_processed}/{total_count} "
                    f"({total_processed/total_count*100:.1f}%) | "
                    f"OK: {self.stats['total_deleted']} | "
                    f"FAIL: {self.stats['total_failed']} | "
                    f"Rate: {rate:.1f}/s | "
                    f"ETA: {eta_minutes:.1f}m"
                )
            
            # Save checkpoint periodically
            if total_processed % Config.CHECKPOINT_INTERVAL == 0:
                self.checkpoint_manager.save_checkpoint(
                    deleted_ids, failed_ids, total_processed, total_count
                )
            
            # Rate limiting
            time.sleep(Config.RATE_LIMIT_DELAY)
        
        # Final checkpoint and summary
        self.stats['end_time'] = datetime.now()
        self.checkpoint_manager.save_checkpoint(
            deleted_ids, failed_ids, len(deleted_ids) + len(failed_ids), total_count
        )
        
        self.print_summary()
        
        # Clear checkpoint if 100% successful
        if self.stats['total_failed'] == 0:
            self.checkpoint_manager.clear_checkpoint()
    
    def print_summary(self):
        """Print deletion summary statistics"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        logger.info("\n" + "="*70)
        logger.info("[SUMMARY] DELETION COMPLETE")
        logger.info("="*70)
        logger.info(f"Total Products Fetched: {self.stats['total_fetched']}")
        logger.info(f"Successfully Deleted:   {self.stats['total_deleted']} [OK]")
        logger.info(f"Failed Deletions:       {self.stats['total_failed']} [FAIL]")
        logger.info(f"Success Rate:           {self.stats['total_deleted']/(self.stats['total_deleted']+self.stats['total_failed'])*100:.2f}%")
        logger.info(f"Total Duration:         {duration/60:.2f} minutes")
        logger.info(f"Average Rate:           {(self.stats['total_deleted']+self.stats['total_failed'])/duration:.2f} deletions/sec")
        logger.info(f"Log File:               {Config.LOG_DIR}/{Config.LOG_FILE}")
        logger.info(f"CSV Log:                {Config.LOG_DIR}/{Config.CSV_LOG_FILE}")
        logger.info("="*70 + "\n")


# ================= MAIN EXECUTION =================

def main():
    """Main execution function"""
    
    print("""
    ===================================================================
           BULK PRODUCT DELETION SCRIPT                           
                                                                   
      WARNING: This will delete 80,000+ products!                 
                                                                   
      Features:                                                    
      - OAuth2 authentication                                      
      - Rate limiting & retry logic                                
      - Progress checkpoints                                       
      - Comprehensive logging                                      
      - Resume capability                                          
    ===================================================================
    """)
    
    # Step 1: Get access token
    print("\n[STEP 1] AUTHENTICATION")
    print("-" * 70)
    print("Please obtain your access token using the Flask OAuth app.")
    print("Run the Flask app and visit: http://localhost:5000/login")
    print()
    
    access_token = input("Enter your access token: ").strip()
    
    if not access_token:
        logger.error("[X] No access token provided. Exiting.")
        return
    
    # Step 2: Initialize OAuth client
    oauth_client = OAuth2Client()
    oauth_client.set_token_manually(access_token)
    
    # Verify token
    if not oauth_client.verify_token():
        logger.error("[X] Token verification failed. Please check your token.")
        return
    
    # Step 3: Confirm deletion
    print("\n[WARNING] CONFIRMATION REQUIRED")
    print("-" * 70)
    confirm = input("Are you sure you want to delete ALL products? (type 'DELETE ALL' to confirm): ")
    
    if confirm != "DELETE ALL":
        logger.info("[X] Deletion cancelled by user.")
        return
    
    # Step 4: Initialize deletion client
    client = ProductDeletionClient(oauth_client)
    
    # Step 5: Fetch all products
    print("\n[STEP 2] FETCHING PRODUCTS")
    print("-" * 70)
    products = client.fetch_all_products()
    
    if not products:
        logger.warning("[!] No products found to delete.")
        return
    
    # Extract product IDs
    product_ids = [str(p.get('id') or p.get('product_id')) for p in products if p.get('id') or p.get('product_id')]
    # product_ids = [6995755]
    logger.info(f"Found {len(product_ids)} products to delete")
    print(f"Found {len(product_ids)} products to delete")
    # print(product_ids)
    
    # Step 6: Final confirmation with count
    print(f"\n[WARNING] FINAL CONFIRMATION: Delete {len(product_ids)} products?")
    final_confirm = input("Type 'YES' to proceed: ")
    
    if final_confirm != "YES":
        logger.info("[X] Deletion cancelled by user.")
        return
    
    # Step 7: Execute bulk deletion
    print("\n[STEP 3] BULK DELETION")
    print("-" * 70)
    client.bulk_delete(product_ids, resume=True)
    logger.info("[OK] Deletion process completed!")


if __name__ == "__main__":
    main()