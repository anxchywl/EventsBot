import pytest
from app.web.routers.favorites import _FAVORITE_RATE_LIMITS, _check_rate_limit as fav_rate_limit
from fastapi import HTTPException
from unittest.mock import MagicMock

class TestUserInteractionsSecurity:
    def test_rate_limit_memory_leak_pruning(self):
        """Test that the rate limit prune logic prevents memory leaks."""
        _FAVORITE_RATE_LIMITS.clear()
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        
        # Manually inflate the dict to trigger pruning
        for i in range(10005):
            _FAVORITE_RATE_LIMITS[f"fake:{i}:host"] = [10.0]
            
        # This hit should trigger pruning
        try:
            fav_rate_limit(mock_request, user_id=1, limit=30, window_seconds=60)
        except HTTPException:
            pass
            
        # Since all old entries were at timestamp 10.0 and cutoff is ~now - 60, they should be pruned
        assert len(_FAVORITE_RATE_LIMITS) < 10000
