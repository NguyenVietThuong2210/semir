"""
App/cnv/api_client.py

Production-ready CNV Loyalty API client.
Handles OAuth2 authorization code flow and API requests.
"""
import logging
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional
from django.core.cache import cache
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
import secrets

logger = logging.getLogger(__name__)


class CNVAPIClient:
    """
    CNV Loyalty API client with automated OAuth2 authentication.
    
    Features:
    - Automated OAuth2 authorization code flow (username/password login)
    - Token caching (30 days)
    - Automatic pagination for bulk data retrieval
    - Support for customers and orders endpoints
    
    Usage:
        client = CNVAPIClient(username="user@example.com", password="secret")
        customers = client.fetch_all_customers(max_pages=5)
    """
    
    # API configuration
    PAGE_SIZE = 100  # Records per page
    
    def __init__(self, username: str, password: str):
        """
        Initialize API client with user credentials.
        
        Args:
            username: CNV account username/email
            password: CNV account password
        """
        self.username = username
        self.password = password
        self.base_url = "https://apis.cnvloyalty.com"
        self.sso_url = "https://id.cnv.vn"
        
        # OAuth2 app credentials (from CNV SDK)
        self.client_id = "4e399845e7944241927e77e837794f1e"
        self.client_secret = "a4ba379b7037426b9fbb0455725c5979"
        self.redirect_uri = "http://localhost:5000/callback"
        
        logger.info(f"CNVAPIClient initialized for user: {username}")
    
    def _get_cached_token(self) -> Optional[str]:
        """Retrieve cached access token if available and valid."""
        cache_key = f'cnv_token_{self.username}'
        return cache.get(cache_key)
    
    def _cache_token(self, token: str, expires_in: int):
        """
        Cache access token with expiration.
        
        Args:
            token: Access token to cache
            expires_in: Token lifetime in seconds
        """
        cache_key = f'cnv_token_{self.username}'
        cache_duration = max(expires_in - 300, 300)  # 5 min buffer
        cache.set(cache_key, token, cache_duration)
        logger.info(f"Token cached (expires in ~{expires_in/86400:.0f} days)")
    
    def authenticate(self) -> str:
        """
        Authenticate and obtain access token via OAuth2 authorization code flow.
        
        Returns:
            Access token string
        """
        # Check cache first
        cached = self._get_cached_token()
        if cached:
            logger.info("Using cached token")
            return cached
        
        logger.info("Starting OAuth2 authentication...")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        try:
            # Step 1: Initiate OAuth flow
            state = secrets.token_urlsafe(32)
            oauth_params = {
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'response_type': 'code',
                'scope': 'read_products,write_products,read_customers,write_customers,read_orders,write_orders',
                'state': state
            }
            
            oauth_url = f"{self.sso_url}/oauth"
            response = session.get(oauth_url, params=oauth_params, allow_redirects=True)
            logger.info(f"OAuth initiated (status: {response.status_code})")
            
            # Step 2: Parse login form
            soup = BeautifulSoup(response.content, 'html.parser')
            form = soup.find('form')
            
            if not form:
                raise ValueError("Login form not found")
            
            # Get form action URL
            form_action = form.get('action', '')
            if form_action:
                if form_action.startswith('http'):
                    login_url = form_action
                elif form_action.startswith('/'):
                    login_url = f"{self.sso_url}{form_action}"
                else:
                    login_url = f"{self.sso_url}/{form_action}"
            else:
                login_url = response.url
            
            # Build form data from actual form fields
            form_data = {}
            
            # Add all hidden fields
            for hidden_field in form.find_all('input', type='hidden'):
                field_name = hidden_field.get('name')
                field_value = hidden_field.get('value', '')
                if field_name:
                    form_data[field_name] = field_value
            
            # Find username field
            username_field = None
            for input_field in form.find_all('input'):
                input_type = input_field.get('type', '').lower()
                input_name = input_field.get('name', '').lower()
                
                if input_type in ['text', 'email'] or 'user' in input_name or 'email' in input_name or 'login' in input_name:
                    username_field = input_field.get('name')
                    break
            
            # Find password field
            password_field = None
            for input_field in form.find_all('input', type='password'):
                password_field = input_field.get('name')
                break
            
            # Add credentials to form data
            if username_field:
                form_data[username_field] = self.username
            else:
                form_data['username'] = self.username
                form_data['email'] = self.username
            
            if password_field:
                form_data[password_field] = self.password
            else:
                form_data['password'] = self.password
            
            # Step 3: Submit login form
            response = session.post(
                login_url,
                data=form_data,
                allow_redirects=False,  # Don't follow - need to extract code
                timeout=30
            )
            logger.info(f"Login submitted (status: {response.status_code})")
            
            # Step 4: Follow redirects to extract authorization code
            authorization_code = None
            max_redirects = 5
            redirect_count = 0
            
            while redirect_count < max_redirects:
                if response.status_code not in [301, 302, 303, 307, 308]:
                    break
                
                redirect_url = response.headers.get('Location', '')
                if not redirect_url:
                    break
                
                # Make redirect URL absolute
                if redirect_url.startswith('http'):
                    full_redirect_url = redirect_url
                elif redirect_url.startswith('/'):
                    full_redirect_url = f"{self.sso_url}{redirect_url}"
                else:
                    full_redirect_url = f"{self.sso_url}/{redirect_url}"
                
                # Parse query parameters from redirect URL
                parsed = urlparse(full_redirect_url)
                query_params = parse_qs(parsed.query)
                
                # Check if code is in this redirect
                code_in_url = query_params.get('code', [None])[0]
                if code_in_url:
                    authorization_code = code_in_url
                    logger.info(f"Authorization code obtained (redirect #{redirect_count + 1})")
                    break
                
                # Follow this redirect
                response = session.get(
                    full_redirect_url,
                    allow_redirects=False,
                    timeout=30
                )
                
                redirect_count += 1
            
            if not authorization_code:
                raise ValueError("Failed to obtain authorization code")
            
            # Step 5: Exchange code for access token
            token_params = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri,
                'code': authorization_code
            }
            
            token_url = f"{self.sso_url}/oauth/token"
            token_response = requests.get(
                token_url,
                params=token_params,
                timeout=30
            )
            
            if token_response.status_code != 200:
                raise ValueError(f"Token exchange failed: {token_response.status_code}")
            
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 2592000)
            
            if not access_token:
                raise ValueError("No access token in response")
            
            self._cache_token(access_token, expires_in)
            logger.info("Authentication successful")
            
            return access_token
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise
        finally:
            session.close()
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make authenticated API request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional request parameters
            
        Returns:
            Parsed JSON response
        """
        token = self.authenticate()
        
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop('headers', {})
        headers.update({
            'Authorization': f'TOKEN {token}',
            'Accept': 'application/json',
        })
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=60,
            **kwargs
        )
        
        if response.status_code != 200:
            logger.error(f"API error {response.status_code}: {response.text[:200]}")
            response.raise_for_status()
        
        return response.json()
    
    def get_customers(self, page: int = 1, page_size: int = 100,
                     updated_since: Optional[datetime] = None,
                     ids: Optional[List[int]] = None) -> Dict:
        """
        Fetch single page of customers.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of records per page
            updated_since: Only return customers updated after this datetime
            ids: List of customer IDs to fetch (max 100)
            
        Returns:
            API response dict with customer data
        """
        params = {
            'page': page,
            'per_page': page_size,
            'limit': page_size
        }
        
        if ids:
            # Pass ids as comma-separated string
            params['ids'] = ','.join(map(str, ids))
        
        if updated_since:
            # Format datetime for API (use Z suffix for UTC)
            if updated_since.tzinfo is not None:
                # Convert to UTC and format with Z suffix
                utc_dt = updated_since.astimezone(timezone.utc)
                params['updated_at_from'] = utc_dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                # Assume UTC if naive
                params['updated_at_from'] = updated_since.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        # Try .json endpoint first (per Swagger docs)
        for endpoint in ['/customers.json', '/api/customers']:
            try:
                return self._make_request('GET', endpoint, params=params)
            except Exception as e:
                logger.warning(f"{endpoint} failed: {e}")
                continue
        
        raise ValueError("All customer endpoints failed")
    
    def get_orders(self, page: int = 1, page_size: int = 100,
                  start_date: Optional[datetime] = None,
                  end_date: Optional[datetime] = None,
                  updated_since: Optional[datetime] = None,
                  updated_until: Optional[datetime] = None) -> Dict:
        """
        Fetch single page of orders.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of records per page
            start_date: Filter orders from this date
            end_date: Filter orders until this date
            updated_since: Only return orders updated after this datetime
            updated_until: Only return orders updated before this datetime
            
        Returns:
            API response dict with order data
        """
        params = {
            'page': page,
            'per_page': page_size,
            'limit': page_size
        }
        
        if start_date:
            params['start_date'] = start_date.strftime('%Y-%m-%d')
        if end_date:
            params['end_date'] = end_date.strftime('%Y-%m-%d')
        if updated_since:
            # Format datetime for API (use Z suffix for UTC)
            if updated_since.tzinfo is not None:
                # Convert to UTC and format with Z suffix
                utc_dt = updated_since.astimezone(timezone.utc)
                params['updated_at_from'] = utc_dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                # Assume UTC if naive
                params['updated_at_from'] = updated_since.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if updated_until:
            # Format datetime for API (use Z suffix for UTC)
            if updated_until.tzinfo is not None:
                utc_dt = updated_until.astimezone(timezone.utc)
                params['updated_at_to'] = utc_dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                params['updated_at_to'] = updated_until.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        # Try .json endpoint first (per Swagger docs)
        for endpoint in ['/orders.json', '/api/orders']:
            try:
                return self._make_request('GET', endpoint, params=params)
            except Exception as e:
                logger.warning(f"{endpoint} failed: {e}")
                continue
        
        raise ValueError("All order endpoints failed")
    
    def fetch_all_customers(self, updated_since: Optional[datetime] = None,
                           max_pages: Optional[int] = None) -> List[Dict]:
        """
        Fetch customers with max 100 pages per sync (API limit).
        
        Strategy:
        - Sort by updated_at ascending (oldest first)
        - Fetch max 100 pages (10,000 records)
        - Track latest updated_at as checkpoint
        - Next sync continues from checkpoint
        
        Args:
            updated_since: Continue from this checkpoint (updated_at)
            max_pages: Override max pages (default: 100)
            
        Returns:
            List of customer dicts
        """
        if max_pages is None:
            max_pages = 100  # API limit
        
        logger.info(f"Fetching customers (max {max_pages} pages, checkpoint: {updated_since})")
        
        all_customers = []
        page = 1
        
        while page <= max_pages:
            try:
                response = self.get_customers(
                    page=page,
                    page_size=self.PAGE_SIZE,
                    updated_since=updated_since
                )
                
                # Extract customers from response
                customers = []
                if isinstance(response, list):
                    customers = response
                elif isinstance(response, dict):
                    customers = response.get('data') or response.get('customers') or []
                
                if not customers:
                    logger.info(f"  Page {page}: No more customers")
                    break
                
                all_customers.extend(customers)
                logger.info(f"  Page {page}: {len(customers)} customers (total: {len(all_customers)})")
                
                # Check if more pages exist
                has_more = False
                if isinstance(response, dict):
                    pagination = response.get('pagination', {})
                    has_more = pagination.get('has_more') or pagination.get('hasMore') or False
                    
                    if not pagination and len(customers) >= self.PAGE_SIZE:
                        has_more = True
                
                if not has_more:
                    logger.info(f"  No more pages available")
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break
        
        if page >= max_pages:
            logger.info(f"Reached max pages limit ({max_pages})")
        
        logger.info(f"Fetched {len(all_customers)} customers ({page-1} pages)")
        return all_customers
    
    def fetch_customers_by_ids(self, customer_ids: List[int], batch_size: int = 100) -> List[Dict]:
        """
        Fetch customers by their IDs in batches.
        
        Args:
            customer_ids: List of customer IDs
            batch_size: Number of IDs per API call (max 100)
            
        Returns:
            List of customer dicts
        """
        logger.info(f"Fetching {len(customer_ids)} customers by IDs...")
        all_customers = []
        
        # Process in batches of 100 IDs
        for i in range(0, len(customer_ids), batch_size):
            batch_ids = customer_ids[i:i + batch_size]
            
            try:
                response = self.get_customers(ids=batch_ids)
                
                # Extract customers from response
                customers = []
                if isinstance(response, list):
                    customers = response
                elif isinstance(response, dict):
                    customers = response.get('data') or response.get('customers') or []
                
                all_customers.extend(customers)
                logger.info(f"  Batch {i//batch_size + 1}: {len(customers)} customers (total: {len(all_customers)})")
                
            except Exception as e:
                logger.error(f"Failed to fetch batch {i//batch_size + 1}: {e}")
                continue
        
        logger.info(f"Fetched {len(all_customers)} customers by IDs")
        return all_customers
    
    def fetch_all_orders(self, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None,
                        updated_since: Optional[datetime] = None,
                        updated_until: Optional[datetime] = None,
                        max_pages: Optional[int] = None) -> List[Dict]:
        """
        Fetch orders with max 100 pages per sync (API limit).
        
        Strategy:
        - Fetch max 100 pages (10,000 records)
        - Use updated_at_from and updated_at_to to scan by date range
        - Next sync continues from checkpoint
        
        Args:
            start_date: Filter orders from this date
            end_date: Filter orders until this date
            updated_since: Continue from this checkpoint (updated_at)
            updated_until: Stop at this datetime (updated_at)
            max_pages: Override max pages (default: 100)
            
        Returns:
            List of order dicts
        """
        if max_pages is None:
            max_pages = 100  # API limit
        
        logger.info(f"Fetching orders (max {max_pages} pages, checkpoint: {updated_since}, until: {updated_until})")
        
        all_orders = []
        page = 1
        
        while page <= max_pages:
            try:
                response = self.get_orders(
                    page=page,
                    page_size=self.PAGE_SIZE,
                    start_date=start_date,
                    end_date=end_date,
                    updated_since=updated_since,
                    updated_until=updated_until
                )
                
                # Extract orders from response
                orders = []
                if isinstance(response, list):
                    orders = response
                elif isinstance(response, dict):
                    orders = response.get('data') or response.get('orders') or []
                
                if not orders:
                    logger.info(f"  Page {page}: No more orders")
                    break
                
                all_orders.extend(orders)
                logger.info(f"  Page {page}: {len(orders)} orders (total: {len(all_orders)})")
                
                # Check if more pages exist
                has_more = False
                if isinstance(response, dict):
                    pagination = response.get('pagination', {})
                    has_more = pagination.get('has_more') or pagination.get('hasMore') or False
                    
                    if not pagination and len(orders) >= self.PAGE_SIZE:
                        has_more = True
                
                if not has_more:
                    logger.info(f"  No more pages available")
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break
        
        if page >= max_pages:
            logger.info(f"Reached max pages limit ({max_pages})")
        
        logger.info(f"Fetched {len(all_orders)} orders ({page-1} pages)")
        return all_orders