"""Tavily API client for web search."""
import logging
from typing import Optional, List, Dict, Any
import aiohttp

logger = logging.getLogger(__name__)


class TavilyAPI:
    """Client for Tavily Search API."""
    
    def __init__(self, api_key: str):
        """Initialize Tavily API client.
        
        Args:
            api_key: Tavily API key
        """
        self.api_key = api_key
        self.base_url = "https://api.tavily.com"
    
    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        include_raw_content: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Perform web search using Tavily API.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return (default: 5)
            search_depth: Search depth - "basic" or "advanced" (default: "basic")
            include_answer: Include AI-generated answer (default: True)
            include_raw_content: Include raw HTML content (default: False)
            
        Returns:
            Search results dict or None on error
        """
        if not self.api_key:
            logger.error("Tavily API key not configured")
            return None
        
        url = f"{self.base_url}/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Tavily search successful for query: {query}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Tavily API error {response.status}: {error_text}")
                        return None
        except aiohttp.ClientError as e:
            logger.error(f"Tavily API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error in Tavily search: {str(e)}")
            return None
    
    def format_results(self, search_data: Dict[str, Any]) -> str:
        """Format search results for AI consumption.
        
        Args:
            search_data: Raw search results from Tavily API
            
        Returns:
            Formatted string with search results
        """
        if not search_data:
            return "No search results found"
        
        formatted = []
        
        # Add AI-generated answer if available
        if "answer" in search_data and search_data["answer"]:
            formatted.append(f"Answer: {search_data['answer']}\n")
        
        # Add search results
        results = search_data.get("results", [])
        if results:
            formatted.append("Search Results:")
            for i, result in enumerate(results, 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                content = result.get("content", "")
                
                formatted.append(f"\n{i}. {title}")
                if url:
                    formatted.append(f"   URL: {url}")
                if content:
                    formatted.append(f"   {content}")
        
        return "\n".join(formatted) if formatted else "No search results found"
