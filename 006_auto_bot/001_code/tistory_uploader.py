import requests
from datetime import datetime
from typing import Dict, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TistoryUploader:
    """Tistory blog API uploader"""

    def __init__(self, access_token: str, blog_name: str):
        """
        Initialize TistoryUploader

        Args:
            access_token: Tistory API access token
            blog_name: Tistory blog name (e.g., 'myblog')
        """
        self.access_token = access_token
        self.blog_name = blog_name
        self.base_url = "https://www.tistory.com/apis"

    def upload_post(
        self,
        title: str,
        content: str,
        visibility: int = 0,
        category: Optional[str] = None,
        tag: Optional[str] = None
    ) -> Dict:
        """
        Upload a post to Tistory blog

        Args:
            title: Post title
            content: Post content (HTML format)
            visibility: 0=비공개, 1=보호, 3=발행 (default: 0)
            category: Category ID (optional)
            tag: Comma-separated tags (optional)

        Returns:
            Response dictionary with post information
        """
        try:
            url = f"{self.base_url}/post/write"

            # Prepare request data
            data = {
                'access_token': self.access_token,
                'output': 'json',
                'blogName': self.blog_name,
                'title': title,
                'content': content,
                'visibility': visibility,
            }

            # Add optional parameters
            if category:
                data['category'] = category

            if tag:
                data['tag'] = tag

            # Make POST request
            logger.info(f"Uploading post to Tistory: {title[:50]}...")
            response = requests.post(url, data=data)
            response.raise_for_status()

            result = response.json()

            if result.get('tistory', {}).get('status') == '200':
                post_id = result['tistory']['postId']
                post_url = result['tistory']['url']
                logger.info(f"Successfully uploaded post. Post ID: {post_id}")
                logger.info(f"Post URL: {post_url}")

                return {
                    'success': True,
                    'post_id': post_id,
                    'url': post_url,
                    'message': 'Post uploaded successfully'
                }
            else:
                error_msg = result.get('tistory', {}).get('error_message', 'Unknown error')
                logger.error(f"Failed to upload post: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while uploading post: {str(e)}")
            return {
                'success': False,
                'message': f'Network error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error while uploading post: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def get_category_list(self) -> Dict:
        """
        Get list of blog categories

        Returns:
            Dictionary containing category information
        """
        try:
            url = f"{self.base_url}/category/list"

            params = {
                'access_token': self.access_token,
                'output': 'json',
                'blogName': self.blog_name
            }

            logger.info("Fetching category list from Tistory...")
            response = requests.get(url, params=params)
            response.raise_for_status()

            result = response.json()

            if result.get('tistory', {}).get('status') == '200':
                categories = result['tistory']['item']['categories']
                logger.info(f"Successfully fetched {len(categories)} categories")
                return {
                    'success': True,
                    'categories': categories
                }
            else:
                error_msg = result.get('tistory', {}).get('error_message', 'Unknown error')
                logger.error(f"Failed to fetch categories: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Error fetching categories: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def modify_post(
        self,
        post_id: str,
        title: str,
        content: str,
        visibility: int = 3,
        category: Optional[str] = None,
        tag: Optional[str] = None
    ) -> Dict:
        """
        Modify an existing post

        Args:
            post_id: Post ID to modify
            title: New post title
            content: New post content (HTML format)
            visibility: 0=비공개, 1=보호, 3=발행 (default: 3)
            category: Category ID (optional)
            tag: Comma-separated tags (optional)

        Returns:
            Response dictionary
        """
        try:
            url = f"{self.base_url}/post/modify"

            data = {
                'access_token': self.access_token,
                'output': 'json',
                'blogName': self.blog_name,
                'postId': post_id,
                'title': title,
                'content': content,
                'visibility': visibility,
            }

            if category:
                data['category'] = category

            if tag:
                data['tag'] = tag

            logger.info(f"Modifying post ID: {post_id}")
            response = requests.post(url, data=data)
            response.raise_for_status()

            result = response.json()

            if result.get('tistory', {}).get('status') == '200':
                logger.info(f"Successfully modified post ID: {post_id}")
                return {
                    'success': True,
                    'post_id': post_id,
                    'message': 'Post modified successfully'
                }
            else:
                error_msg = result.get('tistory', {}).get('error_message', 'Unknown error')
                logger.error(f"Failed to modify post: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg
                }

        except Exception as e:
            logger.error(f"Error modifying post: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
