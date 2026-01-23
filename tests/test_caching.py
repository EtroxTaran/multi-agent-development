"""Tests for prompt caching module.

Covers cache operations, TTL expiration, eviction policies,
statistics tracking, and conversation compression.
"""

import time
from datetime import datetime, timedelta

import pytest

from orchestrator.utils.caching import (
    CacheEntry,
    CacheStats,
    CacheStrategy,
    ConversationCompressor,
    PromptCache,
)

# =============================================================================
# Cache Strategy Tests
# =============================================================================


class TestCacheStrategy:
    """Tests for CacheStrategy enum."""

    def test_strategy_values(self):
        """Test cache strategy enum values."""
        assert CacheStrategy.EXACT.value == "exact"
        assert CacheStrategy.PREFIX.value == "prefix"
        assert CacheStrategy.SEMANTIC.value == "semantic"


# =============================================================================
# Cache Entry Tests
# =============================================================================


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_not_expired(self):
        """Test entry that hasn't expired."""
        entry = CacheEntry(
            prompt_hash="abc123",
            response="test response",
            model="gpt-4.5-turbo",
            timestamp=datetime.now().isoformat(),
            ttl_seconds=3600,
        )

        assert entry.is_expired() is False

    def test_is_expired_expired(self):
        """Test entry that has expired."""
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        entry = CacheEntry(
            prompt_hash="abc123",
            response="test response",
            model="gpt-4.5-turbo",
            timestamp=old_time,
            ttl_seconds=3600,  # 1 hour TTL
        )

        assert entry.is_expired() is True

    def test_is_expired_zero_ttl(self):
        """Test entry with zero TTL is immediately expired."""
        entry = CacheEntry(
            prompt_hash="abc123",
            response="test response",
            model="gpt-4.5-turbo",
            timestamp=datetime.now().isoformat(),
            ttl_seconds=0,
        )

        assert entry.is_expired() is True

    def test_to_dict(self):
        """Test serialization to dict."""
        entry = CacheEntry(
            prompt_hash="abc123",
            response="test response",
            model="gpt-4.5-turbo",
            timestamp="2026-01-21T10:00:00",
            ttl_seconds=3600,
            hit_count=5,
            token_count=100,
            cost_saved=0.05,
            metadata={"key": "value"},
        )

        d = entry.to_dict()

        assert d["prompt_hash"] == "abc123"
        assert d["response"] == "test response"
        assert d["model"] == "gpt-4.5-turbo"
        assert d["ttl_seconds"] == 3600
        assert d["hit_count"] == 5
        assert d["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "prompt_hash": "xyz789",
            "response": "cached response",
            "model": "gemini-3-flash",
            "timestamp": "2026-01-21T10:00:00",
            "ttl_seconds": 7200,
            "hit_count": 3,
            "token_count": 50,
            "cost_saved": 0.02,
            "metadata": {},
        }

        entry = CacheEntry.from_dict(data)

        assert entry.prompt_hash == "xyz789"
        assert entry.response == "cached response"
        assert entry.model == "gemini-3-flash"
        assert entry.hit_count == 3

    def test_default_values(self):
        """Test default values for optional fields."""
        entry = CacheEntry(
            prompt_hash="test",
            response="response",
            model="model",
            timestamp="2026-01-21T10:00:00",
            ttl_seconds=3600,
        )

        assert entry.hit_count == 0
        assert entry.token_count == 0
        assert entry.cost_saved == 0.0
        assert entry.metadata == {}


# =============================================================================
# Cache Stats Tests
# =============================================================================


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = CacheStats()

        assert stats.total_requests == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.tokens_saved == 0
        assert stats.estimated_cost_saved == 0.0

    def test_hit_rate_zero_requests(self):
        """Test hit rate when no requests."""
        stats = CacheStats(total_requests=0)

        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(
            total_requests=100,
            cache_hits=75,
            cache_misses=25,
        )

        assert stats.hit_rate == 0.75

    def test_to_dict_includes_hit_rate(self):
        """Test to_dict includes computed hit_rate."""
        stats = CacheStats(
            total_requests=10,
            cache_hits=5,
        )

        d = stats.to_dict()

        assert "hit_rate" in d
        assert d["hit_rate"] == 0.5


# =============================================================================
# Prompt Cache Tests
# =============================================================================


class TestPromptCache:
    """Tests for PromptCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a test prompt cache."""
        return PromptCache(
            cache_dir=tmp_path,
            strategy=CacheStrategy.EXACT,
            max_entries=100,
            default_ttl=3600,
        )

    def test_set_and_get_exact_match(self, cache):
        """Test storing and retrieving exact match."""
        cache.set(
            prompt="Hello, how are you?",
            response="I'm doing well, thank you!",
            model="gpt-4.5-turbo",
        )

        result = cache.get(
            prompt="Hello, how are you?",
            model="gpt-4.5-turbo",
        )

        assert result == "I'm doing well, thank you!"

    def test_cache_miss(self, cache):
        """Test cache miss returns None."""
        result = cache.get(
            prompt="Uncached prompt",
            model="gpt-4.5-turbo",
        )

        assert result is None

    def test_cache_miss_different_model(self, cache):
        """Test cache miss for different model."""
        cache.set(
            prompt="Test prompt",
            response="Test response",
            model="gpt-4.5-turbo",
        )

        result = cache.get(
            prompt="Test prompt",
            model="gemini-3-flash",  # Different model
        )

        assert result is None

    def test_ttl_expiration(self, cache):
        """Test cache entry expires after TTL."""
        # Set with very short TTL
        cache.set(
            prompt="Expiring prompt",
            response="Expiring response",
            model="gpt-4.5-turbo",
            ttl=1,  # 1 second TTL
        )

        # Should be available immediately
        result = cache.get("Expiring prompt", "gpt-4.5-turbo")
        assert result == "Expiring response"

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        result = cache.get("Expiring prompt", "gpt-4.5-turbo")
        assert result is None

    def test_hit_count_increments(self, cache):
        """Test hit count increments on cache hits."""
        cache.set(
            prompt="Popular prompt",
            response="Response",
            model="gpt-4.5-turbo",
        )

        # Multiple gets
        cache.get("Popular prompt", "gpt-4.5-turbo")
        cache.get("Popular prompt", "gpt-4.5-turbo")
        cache.get("Popular prompt", "gpt-4.5-turbo")

        # Check stats
        assert cache.stats.cache_hits == 3

    def test_stats_tracking(self, cache):
        """Test statistics are tracked correctly."""
        cache.set("prompt1", "response1", "model")

        cache.get("prompt1", "model")  # Hit
        cache.get("prompt2", "model")  # Miss
        cache.get("prompt1", "model")  # Hit
        cache.get("prompt3", "model")  # Miss

        assert cache.stats.total_requests == 4
        assert cache.stats.cache_hits == 2
        assert cache.stats.cache_misses == 2

    def test_metadata_storage(self, cache):
        """Test metadata is stored with cache entry."""
        cache.set(
            prompt="Test prompt",
            response="Test response",
            model="gpt-4.5-turbo",
            metadata={"task_type": "validation", "phase": 2},
        )

        # Metadata should be stored (we can check by looking at internal state)
        cache_key = cache._compute_hash("Test prompt", "gpt-4.5-turbo")
        entry = cache._cache.get(cache_key)

        assert entry is not None
        assert entry.metadata["task_type"] == "validation"

    def test_max_entries_eviction(self, tmp_path):
        """Test entries are evicted when max is reached."""
        cache = PromptCache(
            cache_dir=tmp_path,
            max_entries=5,
        )

        # Add 6 entries
        for i in range(6):
            cache.set(f"prompt{i}", f"response{i}", "model")

        # Should have evicted oldest entries
        assert len(cache._cache) <= 5

    def test_invalidate_specific_entry(self, cache):
        """Test invalidating a specific cache entry."""
        cache.set("prompt1", "response1", "model")
        cache.set("prompt2", "response2", "model")

        result = cache.invalidate("prompt1", "model")

        assert result is True
        assert cache.get("prompt1", "model") is None
        assert cache.get("prompt2", "model") == "response2"

    def test_invalidate_nonexistent(self, cache):
        """Test invalidating non-existent entry."""
        result = cache.invalidate("nonexistent", "model")

        assert result is False

    def test_clear_cache(self, cache):
        """Test clearing all cache entries."""
        cache.set("prompt1", "response1", "model")
        cache.set("prompt2", "response2", "model")

        cache.clear()

        assert len(cache._cache) == 0
        assert cache.get("prompt1", "model") is None

    def test_cleanup_expired(self, cache):
        """Test cleanup removes expired entries."""
        # Add entry with short TTL
        cache.set("expiring", "response", "model", ttl=1)
        # Add entry with long TTL
        cache.set("lasting", "response", "model", ttl=3600)

        time.sleep(1.1)

        removed = cache.cleanup_expired()

        assert removed == 1
        assert cache.get("expiring", "model") is None
        assert cache.get("lasting", "model") == "response"

    def test_persistence(self, tmp_path):
        """Test cache persists across instances."""
        cache1 = PromptCache(cache_dir=tmp_path)
        cache1.set("persisted prompt", "persisted response", "model")

        # Create new instance
        cache2 = PromptCache(cache_dir=tmp_path)

        # Should have loaded cached data
        result = cache2.get("persisted prompt", "model")
        assert result == "persisted response"

    def test_get_stats(self, cache):
        """Test getting statistics."""
        cache.set("prompt", "response", "model")
        cache.get("prompt", "model")

        stats = cache.get_stats()

        assert isinstance(stats, CacheStats)
        assert stats.total_requests == 1

    def test_get_stats_summary(self, cache):
        """Test generating stats summary."""
        cache.set("prompt", "response", "model")
        cache.get("prompt", "model")
        cache.get("other", "model")  # Miss

        summary = cache.get_stats_summary()

        assert "Prompt Cache Statistics" in summary
        assert "Total Requests: 2" in summary
        assert "Cache Hits: 1" in summary
        assert "Hit Rate:" in summary


# =============================================================================
# Prefix Cache Strategy Tests
# =============================================================================


class TestPrefixStrategy:
    """Tests for PREFIX cache strategy."""

    @pytest.fixture
    def prefix_cache(self, tmp_path):
        """Create a cache with prefix strategy."""
        return PromptCache(
            cache_dir=tmp_path,
            strategy=CacheStrategy.PREFIX,
        )

    def test_prefix_match(self, prefix_cache):
        """Test prefix matching ignores content after the prefix threshold.

        The PREFIX strategy uses the first 1000 characters for cache key generation.
        Prompts with identical first 1000 chars but different suffixes should match.
        """
        # Create a common prefix longer than 1000 chars
        common_prefix = "X" * 1001

        prompt1 = common_prefix + " User query: What is 2+2?"
        prompt2 = common_prefix + " User query: What is 3+3?"

        # Set with first prompt
        prefix_cache.set(prompt1, "Response 1", "model")

        # Should match because first 1000 chars are identical
        result = prefix_cache.get(prompt2, "model")

        # With prefix strategy, these should share same cache key
        # since prefix matching uses first 1000 chars
        assert result == "Response 1"

    def test_prefix_no_match_different_prefix(self, prefix_cache):
        """Test prefix strategy doesn't match when prefixes differ."""
        prompt1 = "A" * 500 + " query 1"
        prompt2 = "B" * 500 + " query 2"

        prefix_cache.set(prompt1, "Response 1", "model")

        # Different prefix means cache miss
        result = prefix_cache.get(prompt2, "model")

        assert result is None


# =============================================================================
# Conversation Compressor Tests
# =============================================================================


class TestConversationCompressor:
    """Tests for ConversationCompressor class."""

    @pytest.fixture
    def compressor(self):
        """Create a test compressor."""
        return ConversationCompressor(
            max_recent_turns=3,
            summary_interval=5,
        )

    def test_no_compression_under_threshold(self, compressor):
        """Test messages under threshold aren't compressed."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        result = compressor.compress(messages)

        assert len(result) == 2
        assert result == messages

    def test_compression_over_threshold(self, compressor):
        """Test messages over threshold are compressed."""
        messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        result = compressor.compress(messages)

        # Should have summary + 3 recent turns
        assert len(result) == 4  # 1 summary + 3 recent
        assert result[0]["role"] == "system"
        assert "summary" in result[0]["content"].lower()

    def test_keeps_recent_turns(self, compressor):
        """Test most recent turns are kept in full."""
        messages = [
            {"role": "user", "content": "Old message 1"},
            {"role": "assistant", "content": "Old response 1"},
            {"role": "user", "content": "Recent message 1"},
            {"role": "assistant", "content": "Recent response 1"},
            {"role": "user", "content": "Recent message 2"},
        ]

        result = compressor.compress(messages)

        # Last 3 should be kept
        assert result[-1]["content"] == "Recent message 2"
        assert result[-2]["content"] == "Recent response 1"
        assert result[-3]["content"] == "Recent message 1"

    def test_basic_summary_extraction(self, compressor):
        """Test basic summary extracts first sentences."""
        older = [
            {"role": "user", "content": "First sentence. More content here."},
            {"role": "assistant", "content": "Response sentence. Additional info."},
        ]

        summary = compressor._basic_summary(older)

        assert "user" in summary
        assert "First sentence" in summary
        assert "assistant" in summary

    def test_custom_summarizer(self, compressor):
        """Test using custom summarizer function."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "Recent"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Latest"},
        ]

        def custom_summarizer(msgs):
            return f"Custom summary of {len(msgs)} messages"

        result = compressor.compress(messages, summarizer_fn=custom_summarizer)

        assert "Custom summary" in result[0]["content"]

    def test_estimate_savings(self, compressor):
        """Test token savings estimation."""
        original = [
            {"role": "user", "content": "A" * 400},  # ~100 tokens
            {"role": "assistant", "content": "B" * 400},
            {"role": "user", "content": "C" * 400},
            {"role": "assistant", "content": "D" * 400},
            {"role": "user", "content": "E" * 100},
        ]

        compressed = compressor.compress(original)

        savings = compressor.estimate_savings(original, compressed)

        assert "original_tokens" in savings
        assert "compressed_tokens" in savings
        assert "tokens_saved" in savings
        assert "savings_pct" in savings

        # Should have some savings
        assert savings["tokens_saved"] >= 0

    def test_estimate_savings_no_compression(self, compressor):
        """Test savings estimation when no compression needed."""
        messages = [
            {"role": "user", "content": "Hello"},
        ]

        compressed = compressor.compress(messages)

        savings = compressor.estimate_savings(messages, compressed)

        # Same messages, no savings
        assert savings["tokens_saved"] == 0
        assert savings["savings_pct"] == 0

    def test_empty_messages(self, compressor):
        """Test handling empty message list."""
        result = compressor.compress([])

        assert result == []

    def test_empty_content(self, compressor):
        """Test handling messages with empty content."""
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant"},  # Missing content
        ]

        # Should handle gracefully
        summary = compressor._basic_summary(messages)
        assert isinstance(summary, str)


# =============================================================================
# Token Costs Tests
# =============================================================================


class TestTokenCosts:
    """Tests for token cost calculations in cache."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a test cache."""
        return PromptCache(cache_dir=tmp_path)

    def test_cost_estimation_known_model(self, cache):
        """Test cost estimation for known model."""
        cost = cache._estimate_cost(
            model="gpt-4.5-turbo",
            input_tokens=1000,
            output_tokens=1000,
        )

        # (1000/1000 * 0.005) + (1000/1000 * 0.015) = 0.02
        assert cost == pytest.approx(0.02)

    def test_cost_estimation_unknown_model(self, cache):
        """Test cost estimation for unknown model uses defaults."""
        cost = cache._estimate_cost(
            model="unknown-model",
            input_tokens=1000,
            output_tokens=1000,
        )

        # Default: (1000/1000 * 0.01) + (1000/1000 * 0.03) = 0.04
        assert cost == pytest.approx(0.04)

    def test_token_estimation(self, cache):
        """Test token count estimation."""
        text = "A" * 400  # 400 chars

        tokens = cache._estimate_tokens(text)

        # Approx 4 chars per token
        assert tokens == 100

    def test_cost_saved_tracking(self, cache):
        """Test cost saved is tracked on cache hits."""
        cache.set("prompt", "response", "gpt-4.5-turbo")

        # Multiple hits
        cache.get("prompt", "gpt-4.5-turbo")
        cache.get("prompt", "gpt-4.5-turbo")

        assert cache.stats.estimated_cost_saved > 0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_hash_collision_prevention(self, tmp_path):
        """Test different prompts produce different hashes."""
        cache = PromptCache(cache_dir=tmp_path)

        hash1 = cache._compute_hash("prompt1", "model")
        hash2 = cache._compute_hash("prompt2", "model")

        assert hash1 != hash2

    def test_model_in_hash(self, tmp_path):
        """Test model name is included in hash."""
        cache = PromptCache(cache_dir=tmp_path)

        hash1 = cache._compute_hash("prompt", "model1")
        hash2 = cache._compute_hash("prompt", "model2")

        assert hash1 != hash2

    def test_load_corrupted_cache(self, tmp_path):
        """Test loading corrupted cache file."""
        cache_file = tmp_path / "prompt_cache.json"
        cache_file.write_text("not valid json")

        # Should handle gracefully
        cache = PromptCache(cache_dir=tmp_path)

        assert len(cache._cache) == 0
        assert cache.stats.total_requests == 0

    def test_evict_oldest_empty_cache(self, tmp_path):
        """Test eviction on empty cache doesn't error."""
        cache = PromptCache(cache_dir=tmp_path, max_entries=5)

        # Should not error
        cache._evict_oldest()

        assert len(cache._cache) == 0

    def test_very_long_prompt(self, tmp_path):
        """Test handling very long prompts."""
        cache = PromptCache(cache_dir=tmp_path)

        long_prompt = "x" * 100000  # 100K characters

        cache.set(long_prompt, "response", "model")
        result = cache.get(long_prompt, "model")

        assert result == "response"

    def test_special_characters_in_prompt(self, tmp_path):
        """Test handling special characters in prompts."""
        cache = PromptCache(cache_dir=tmp_path)

        special_prompt = "Hello! 你好 🎉 \n\t\"quotes\" and 'apostrophes'"

        cache.set(special_prompt, "response", "model")
        result = cache.get(special_prompt, "model")

        assert result == "response"

    def test_concurrent_access_simulation(self, tmp_path):
        """Test cache handles rapid access."""
        cache = PromptCache(cache_dir=tmp_path)

        # Rapid set/get operations
        for i in range(100):
            cache.set(f"prompt{i}", f"response{i}", "model")
            cache.get(f"prompt{i}", "model")

        assert cache.stats.cache_hits == 100
        assert cache.stats.total_requests == 100
