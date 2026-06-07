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
        
        # force pruning path without waiting for real traffic
        for i in range(10005):
            _FAVORITE_RATE_LIMITS[f"fake:{i}:host"] = [10.0]
            
        try:
            fav_rate_limit(mock_request, user_id=1, limit=30, window_seconds=60)
        except HTTPException:
            pass
            
        # old timestamps should be removed after the next hit
        assert len(_FAVORITE_RATE_LIMITS) < 10000
