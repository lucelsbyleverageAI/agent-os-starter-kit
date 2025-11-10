"""Outlook email client via Microsoft Graph API."""

import os
from typing import Any, Dict, Optional, List
from datetime import datetime
import httpx
import dotenv

from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError, AuthorizationError

dotenv.load_dotenv()
logger = get_logger(__name__)


class OutlookAPIError(Exception):
    """Outlook/Graph API specific error."""
    pass


class OutlookClient:
    """Microsoft Graph API client for Outlook operations."""

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.tenant_id = tenant_id or os.getenv("MICROSOFT_GRAPH_TENANT_ID")
        self.client_id = client_id or os.getenv("MICROSOFT_GRAPH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("MICROSOFT_GRAPH_CLIENT_SECRET")

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise AuthorizationError(
                "Microsoft Graph credentials not found. Please set "
                "MICROSOFT_GRAPH_TENANT_ID, MICROSOFT_GRAPH_CLIENT_ID, "
                "and MICROSOFT_GRAPH_CLIENT_SECRET environment variables."
            )

        self.graph_base_url = "https://graph.microsoft.com/v1.0"
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[float] = None

    async def _ensure_access_token(self) -> str:
        """Get or refresh access token using client credentials flow."""
        import time

        # Check if token is still valid (with 5min buffer)
        if self._access_token and self._token_expires_at:
            if time.time() < (self._token_expires_at - 300):
                return self._access_token

        # Request new token
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                    timeout=30.0,
                )

                if response.status_code != 200:
                    raise OutlookAPIError(
                        f"Token acquisition failed: HTTP {response.status_code}: {response.text}"
                    )

                data = response.json()
                self._access_token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 3600)

                logger.info("Successfully acquired Graph API access token")
                return self._access_token

        except httpx.RequestError as e:
            raise ToolExecutionError(
                "outlook_client", f"Token request failed: {str(e)}"
            )

    async def _graph_request(
        self,
        method: str,
        endpoint: str,
        user_email: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to Graph API."""
        token = await self._ensure_access_token()

        request_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)

        # Replace {userPrincipalName} placeholder
        full_endpoint = endpoint.replace("{userPrincipalName}", user_email)
        url = f"{self.graph_base_url}{full_endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=request_headers,
                    timeout=60.0,
                )

                if response.status_code == 401:
                    raise AuthorizationError("Invalid Graph API credentials")

                if response.status_code == 403:
                    raise AuthorizationError(
                        f"Insufficient permissions to access {user_email}'s mailbox"
                    )

                if response.status_code == 404:
                    raise OutlookAPIError(f"Resource not found: {endpoint}")

                # 202 Accepted for async operations (send email)
                if response.status_code == 202:
                    return {"status": "accepted"}

                # 204 No Content
                if response.status_code == 204:
                    return {}

                if response.status_code not in (200, 201):
                    raise OutlookAPIError(
                        f"HTTP {response.status_code}: {response.text}"
                    )

                return response.json() if response.content else {}

        except httpx.TimeoutException:
            raise ToolExecutionError(
                "outlook_client", "Request to Graph API timed out"
            )
        except httpx.RequestError as e:
            raise ToolExecutionError(
                "outlook_client", f"Request to Graph API failed: {str(e)}"
            )

    async def list_messages(
        self,
        user_email: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sender: Optional[str] = None,
        subject_keyword: Optional[str] = None,
        body_keyword: Optional[str] = None,
        folder_id: Optional[str] = None,
        limit: int = 20,
        next_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List messages with filtering across all folders or specific folder.

        Uses KQL-based $search for optimal performance when filtering.
        $search uses Exchange Search service which is highly optimized for mailbox queries.

        Uses cursor-based pagination via next_link for optimal performance.
        The $skip parameter has been removed as it causes severe performance issues.

        Note: Recipient filtering has been removed due to Graph API complexity limits.
        Filter results client-side if recipient filtering is needed.
        """

        # If next_link is provided, use it directly (cursor-based pagination)
        if next_link:
            # Extract the full URL path and query from next_link
            # next_link format: "https://graph.microsoft.com/v1.0/users/{email}/messages?$skiptoken=..."
            import urllib.parse
            parsed = urllib.parse.urlparse(next_link)
            endpoint = parsed.path.replace("/v1.0", "")  # Remove base path

            # Make request with the skiptoken from nextLink
            return await self._graph_request(
                method="GET",
                endpoint=endpoint,
                user_email=user_email,
                params=dict(urllib.parse.parse_qsl(parsed.query)),
            )

        # Build endpoint for initial request
        if folder_id:
            endpoint = f"/users/{{userPrincipalName}}/mailFolders/{folder_id}/messages"
        else:
            endpoint = "/users/{userPrincipalName}/messages"

        # Build query parameters
        params = {
            "$top": min(limit, 1000),  # Max 1000
            "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,hasAttachments,bodyPreview,isRead,importance",
        }

        # Build KQL-based $search query for optimal performance
        # KQL syntax allows combining date filters, sender, and keywords in a single optimized query
        # This performs much better than $filter for complex multi-condition queries
        #
        # IMPORTANT: When using $search, we add sortBy to KQL query to ensure newest-first order
        # When NOT using $search, we can use $orderby parameter
        search_parts = []

        # Helper function to convert ISO 8601 date to KQL format (YYYY-MM-DD)
        def to_kql_date(iso_date: str) -> str:
            """Convert ISO 8601 datetime to KQL date format."""
            # Extract date portion (YYYY-MM-DD) from ISO format
            return iso_date.split('T')[0]

        # Date range filter
        if from_date and to_date:
            # Use KQL date range syntax: received:YYYY-MM-DD..YYYY-MM-DD
            search_parts.append(f"received:{to_kql_date(from_date)}..{to_kql_date(to_date)}")
        elif from_date:
            # Greater than or equal
            search_parts.append(f"received>={to_kql_date(from_date)}")
        elif to_date:
            # Less than or equal
            search_parts.append(f"received<={to_kql_date(to_date)}")

        # Sender filter
        if sender:
            # KQL from: syntax supports email addresses, display names, or aliases
            search_parts.append(f"from:{sender}")

        # Keyword filters
        keyword_parts = []
        if subject_keyword:
            keyword_parts.append(f"subject:{subject_keyword}")
        if body_keyword:
            keyword_parts.append(f"body:{body_keyword}")

        if keyword_parts:
            # Combine keywords with OR (match either subject or body)
            if len(keyword_parts) > 1:
                search_parts.append(f"({' OR '.join(keyword_parts)})")
            else:
                search_parts.append(keyword_parts[0])

        # Combine all search conditions with AND
        if search_parts:
            # KQL query must be wrapped in quotes
            kql_query = " AND ".join(search_parts)
            params["$search"] = f'"{kql_query}"'

            # IMPORTANT: $search does not support $orderby parameter
            # Results from $search may come back in ascending order (oldest first)
            # We'll sort them client-side below to ensure newest-first order
        else:
            # When NOT using $search, we can add $orderby for explicit sorting
            # This ensures newest-first order when listing without search criteria
            params["$orderby"] = "receivedDateTime desc"

        response = await self._graph_request(
            method="GET",
            endpoint=endpoint,
            user_email=user_email,
            params=params,
        )

        # Sort results by receivedDateTime descending (newest first) to ensure consistent ordering
        # This is necessary because $search doesn't support $orderby and may return results
        # in ascending order or relevance order
        if "value" in response and isinstance(response["value"], list):
            response["value"].sort(
                key=lambda msg: msg.get("receivedDateTime", ""),
                reverse=True  # Descending order (newest first)
            )

        return response

    async def list_mail_folders(
        self,
        user_email: str,
    ) -> Dict[str, Any]:
        """List all mail folders for the user."""
        endpoint = "/users/{userPrincipalName}/mailFolders"

        params = {
            "$select": "id,displayName,totalItemCount,unreadItemCount,parentFolderId",
            "$orderby": "displayName asc",
        }

        return await self._graph_request(
            method="GET",
            endpoint=endpoint,
            user_email=user_email,
            params=params,
        )

    async def get_message(
        self,
        user_email: str,
        message_id: str,
        body_format: str = "text",  # "text" or "html"
    ) -> Dict[str, Any]:
        """Get full message content."""
        endpoint = f"/users/{{userPrincipalName}}/messages/{message_id}"

        headers = {}
        if body_format == "text":
            headers["Prefer"] = 'outlook.body-content-type="text"'

        return await self._graph_request(
            method="GET",
            endpoint=endpoint,
            user_email=user_email,
            headers=headers,
        )

    async def get_message_attachments(
        self,
        user_email: str,
        message_id: str,
    ) -> Dict[str, Any]:
        """Get attachment metadata for a message."""
        endpoint = f"/users/{{userPrincipalName}}/messages/{message_id}/attachments"

        params = {
            "$select": "id,name,contentType,size,isInline",
        }

        return await self._graph_request(
            method="GET",
            endpoint=endpoint,
            user_email=user_email,
            params=params,
        )

    async def download_attachment_binary(
        self,
        user_email: str,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """Download raw attachment content as binary data.

        Uses the /$value endpoint which returns binary content directly.
        Note: Microsoft Graph has a 3 MB size limit for attachment downloads.

        Args:
            user_email: Email address of the mailbox owner
            message_id: ID of the message containing the attachment
            attachment_id: ID of the attachment to download

        Returns:
            Raw binary content of the attachment

        Raises:
            OutlookAPIError: If attachment is too large (> 3 MB) or download fails
            AuthorizationError: If credentials are invalid or insufficient permissions
            ToolExecutionError: If network request fails
        """
        token = await self._ensure_access_token()

        # Build endpoint with $value to get binary content
        endpoint = f"/users/{user_email}/messages/{message_id}/attachments/{attachment_id}/$value"
        url = f"{self.graph_base_url}{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60.0,
                )

                if response.status_code == 401:
                    raise AuthorizationError("Invalid Graph API credentials")

                if response.status_code == 403:
                    raise AuthorizationError(
                        f"Insufficient permissions to access {user_email}'s mailbox attachments"
                    )

                if response.status_code == 404:
                    raise OutlookAPIError(
                        f"Attachment not found: message_id={message_id}, attachment_id={attachment_id}"
                    )

                if response.status_code == 413:
                    raise OutlookAPIError(
                        "Attachment too large (> 3 MB). Microsoft Graph API limits downloads to 3 MB. "
                        "Please download this attachment manually via Outlook."
                    )

                if response.status_code != 200:
                    raise OutlookAPIError(
                        f"Failed to download attachment: HTTP {response.status_code}: {response.text[:200]}"
                    )

                return response.content

        except httpx.TimeoutException:
            raise ToolExecutionError(
                "outlook_client",
                "Attachment download timed out (> 60 seconds)"
            )
        except httpx.RequestError as e:
            raise ToolExecutionError(
                "outlook_client",
                f"Failed to download attachment: {str(e)}"
            )

    async def create_draft(
        self,
        user_email: str,
        subject: str,
        body_content: str,
        body_format: str = "HTML",
        to_recipients: Optional[List[str]] = None,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        importance: str = "normal",
    ) -> Dict[str, Any]:
        """Create a draft message."""

        def format_recipients(emails: List[str]) -> List[Dict]:
            return [
                {"emailAddress": {"address": email}}
                for email in emails
            ]

        message_body = {
            "subject": subject,
            "body": {
                "contentType": body_format,
                "content": body_content,
            },
            "importance": importance,
        }

        if to_recipients:
            message_body["toRecipients"] = format_recipients(to_recipients)
        if cc_recipients:
            message_body["ccRecipients"] = format_recipients(cc_recipients)
        if bcc_recipients:
            message_body["bccRecipients"] = format_recipients(bcc_recipients)

        return await self._graph_request(
            method="POST",
            endpoint="/users/{userPrincipalName}/messages",
            user_email=user_email,
            json_body=message_body,
        )

    async def update_draft(
        self,
        user_email: str,
        message_id: str,
        subject: Optional[str] = None,
        body_content: Optional[str] = None,
        body_format: Optional[str] = None,
        to_recipients: Optional[List[str]] = None,
        cc_recipients: Optional[List[str]] = None,
        bcc_recipients: Optional[List[str]] = None,
        importance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing draft message."""

        def format_recipients(emails: List[str]) -> List[Dict]:
            return [
                {"emailAddress": {"address": email}}
                for email in emails
            ]

        update_body = {}

        if subject is not None:
            update_body["subject"] = subject
        if body_content is not None:
            update_body["body"] = {
                "contentType": body_format or "HTML",
                "content": body_content,
            }
        # Only include recipient fields if they have actual values (not empty arrays)
        # Empty arrays would clear the recipients, which is not the intended behavior
        if to_recipients is not None and len(to_recipients) > 0:
            update_body["toRecipients"] = format_recipients(to_recipients)
        if cc_recipients is not None and len(cc_recipients) > 0:
            update_body["ccRecipients"] = format_recipients(cc_recipients)
        if bcc_recipients is not None and len(bcc_recipients) > 0:
            update_body["bccRecipients"] = format_recipients(bcc_recipients)
        if importance is not None:
            update_body["importance"] = importance

        return await self._graph_request(
            method="PATCH",
            endpoint=f"/users/{{userPrincipalName}}/messages/{message_id}",
            user_email=user_email,
            json_body=update_body,
        )

    async def send_draft(
        self,
        user_email: str,
        message_id: str,
    ) -> Dict[str, Any]:
        """Send an existing draft message."""
        return await self._graph_request(
            method="POST",
            endpoint=f"/users/{{userPrincipalName}}/messages/{message_id}/send",
            user_email=user_email,
        )


# Global client instance
_outlook_client: Optional[OutlookClient] = None


def get_outlook_client() -> OutlookClient:
    """Get or create Outlook API client instance."""
    global _outlook_client
    if _outlook_client is None:
        _outlook_client = OutlookClient()
    return _outlook_client


def handle_outlook_error(error: Exception) -> str:
    """Standardize error messages for MCP."""
    if isinstance(error, AuthorizationError):
        return f"Authorization error: {str(error)}"
    elif isinstance(error, OutlookAPIError):
        return f"Outlook API error: {str(error)}"
    elif isinstance(error, ToolExecutionError):
        return f"Execution error: {str(error)}"
    else:
        return f"Unexpected error: {str(error)}"
