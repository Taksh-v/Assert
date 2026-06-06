import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class TruthResolver:
    """
    Adjusts retrieved chunk scores based on source trust authority rankings.
    Official Wikis/Notion/Databases = 1.0
    Jira/GitHub tickets = 0.8
    Slack/Emails = 0.5
    
    Filters out chunks whose weighted scores drop below 0.4.
    """
    
    @staticmethod
    def resolve_weights(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes a list of retrieved chunks (dicts) and returns the weighted and filtered list.
        """
        from urllib.parse import urlparse
        resolved = []
        for item in results:
            meta = item.get("metadata", {}) or {}
            source_url = str(meta.get("source_url", "")).lower()
            title = str(meta.get("title", "")).lower()
            
            # Determine source type and corresponding trust weight
            weight = 1.0  # Default weight (ERP, Database, Official Wiki)
            
            domain = ""
            if source_url:
                url_to_parse = source_url
                if not url_to_parse.startswith(("http://", "https://")):
                    url_to_parse = "https://" + url_to_parse
                try:
                    domain = urlparse(url_to_parse).netloc.lower()
                except Exception:
                    pass
            
            if any(d in domain for d in ["slack.com", "slack-edge.com"]) or "email" in source_url:
                weight = 0.5
            elif any(d in domain for d in ["jira.atlassian.com", "github.com", "github.io"]):
                weight = 0.8
            elif any(d in domain for d in ["notion.so", "notion.page", "confluence.atlassian.com"]) or "wiki" in title:
                weight = 1.0
                
            # Compute new score
            original_score = float(item.get("score", item.get("final_rank_score", item.get("cross_encoder_score", 0.5))))
            weighted_score = original_score * weight
            
            # Update score fields in the dict
            item["score"] = weighted_score
            if "final_rank_score" in item:
                item["final_rank_score"] = weighted_score
            if "cross_encoder_score" in item:
                item["cross_encoder_score"] = weighted_score
                
            # Filter low-relevance/low-trust items
            if weighted_score >= 0.4:
                resolved.append(item)
            else:
                logger.info(f"Filtered out chunk {item.get('chunk_id')} due to low weighted score: {weighted_score:.2f} (original: {original_score:.2f})")
                
        return resolved
