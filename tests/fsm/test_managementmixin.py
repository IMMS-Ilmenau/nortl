"""Tests for the ManagementMixin context managers in nortl/__init__.py."""

from nortl import Engine


class TestContextManager:
    """Tests for the context() context manager."""

    def test_context_basic_usage(self) -> None:
        """Test that context() context manager properly scopes scratch variables."""
        engine = Engine('test_engine')
        engine.sync()

        with engine.context():
            test = engine.define_scratch(4)
            engine.set(test, 1)
            engine.sync()

        # After exiting context, scratch signal should be released
        assert test.released

    def test_context_multiple_scopes(self) -> None:
        """Test that multiple context scopes work correctly."""
        engine = Engine('test_engine')
        engine.sync()

        with engine.context():
            test1 = engine.define_scratch(4)
            engine.set(test1, 1)
            engine.sync()

        with engine.context():
            test2 = engine.define_scratch(3)
            engine.set(test2, 2)
            engine.sync()

        assert test1.released
        assert test2.released

    def test_context_nesting(self) -> None:
        """Test that nested context managers work correctly."""
        engine = Engine('test_engine')
        engine.sync()

        with engine.context():
            with engine.context():
                test = engine.define_scratch(4)
                engine.set(test, 1)
                engine.sync()
                assert not test.released

            assert test.released


class TestCollapseSyncManager:
    """Tests for the collapse_sync() context manager."""

    def test_collapse_sync_basic_usage(self) -> None:
        """Test that collapse_sync() marks states as collapsable."""
        engine = Engine('test_engine')

        with engine.collapse_sync():
            # Should be collapsable
            assert engine.state_metadata_template['collapsable'] is True

        # After exiting, should still be collapsable
        assert engine.state_metadata_template['collapsable'] is False

    def test_collapse_sync_multiple_calls(self) -> None:
        """Test that collapse_sync can be called multiple times."""
        engine = Engine('test_engine')

        with engine.collapse_sync():
            assert engine.state_metadata_template['collapsable'] is True

        with engine.collapse_sync():
            assert engine.state_metadata_template['collapsable'] is True

        assert engine.state_metadata_template['collapsable'] is False

    def test_collapse_sync_nesting(self) -> None:
        """Test that nested collapse_sync managers work correctly."""
        engine = Engine('test_engine')

        with engine.collapse_sync():
            with engine.collapse_sync():
                assert engine.state_metadata_template['collapsable'] is True

        assert engine.state_metadata_template['collapsable'] is False

    def test_collapse_sync_nesting_with_multiple_calls(self) -> None:
        """Test that nested collapse_sync managers work correctly."""
        engine = Engine('test_engine')

        with engine.collapse_sync():
            with engine.collapse_sync():
                assert engine.state_metadata_template['collapsable'] is True

            # The outer context manager has priority
            assert engine.state_metadata_template['collapsable'] is True

            with engine.collapse_sync():
                assert engine.state_metadata_template['collapsable'] is True

        assert engine.state_metadata_template['collapsable'] is False
