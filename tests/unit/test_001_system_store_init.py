# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the RMTC Project

"""
Unit tests for rmtc_core.System store initialisation logic.

The PR introduced a conditional branch that selects between AGEDatabase
and Neo4jDatabase based on the value of store_config["type"].  These
tests exercise that branch in isolation, without requiring a live database
connection, by supplying all other System dependencies as test doubles.
"""

import unittest
from unittest.mock import MagicMock, patch

from rmtc_core import System
from rmtc_core.track.cypher.age import AGEDatabase
from rmtc_core.track.cypher.neo4j import Neo4jDatabase
from rmtc.system import Logger, ModuleFactory, URI, Mode
from rmtc.objects import Objects
from rmtc.system import Broadcaster


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockConfig:
    """Minimal dict-like config object that returns controlled values."""

    def __init__(self, store_config):
        self._data = {
            # Returning None for non-store sections makes System skip them.
            "rmtc_system": None,
            "rmtc_log": None,
            "rmtc_tracker": None,
            "rmtc_store": store_config,
        }

    def __getitem__(self, key):
        return self._data.get(key, None)


def _make_store_config(store_type, db_name=None, name="rmtc_test"):
    """Return a store_config dict for the given type."""
    cfg = {
        "type": store_type,
        "name": name,
        "uri": "bolt://localhost:7687",
        "username": "user",
        "password": "pass",
    }
    if db_name is not None:
        cfg["db_name"] = db_name
    return cfg


def _build_system_with_store_config(store_config):
    """
    Create a System whose only variable is the store section of the config.

    All other dependencies (tracker, log, factory, …) are supplied so that
    System.__init__ does not attempt to read them from the config file or
    create real infrastructure objects.
    """
    log = Logger()
    factory = ModuleFactory(log=log)
    config = _MockConfig(store_config)

    return System(
        config=config,
        log=log,
        factory=factory,
        tracker=MagicMock(),
        asset_manager=MagicMock(),
        env_manager=MagicMock(),
        broadcaster=Broadcaster(),
        objects=Objects(),
        mode=Mode.PRODUCTION,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSystemStoreInitialisation(unittest.TestCase):
    """Tests for the store-type selection added in this PR."""

    # ------------------------------------------------------------------
    # AGEDatabase branch
    # ------------------------------------------------------------------

    def test_age_store_created_when_type_is_age(self):
        """System must create an AGEDatabase when store_config type is 'age'."""
        system = _build_system_with_store_config(_make_store_config("age"))
        self.assertIsInstance(system.store, AGEDatabase)

    def test_age_store_has_correct_name(self):
        """The AGEDatabase store name must match the configured store name."""
        system = _build_system_with_store_config(
            _make_store_config("age", name="my_graph")
        )
        self.assertEqual(system.store.name, "my_graph")

    def test_age_store_uses_configured_db_name(self):
        """AGEDatabase must use the db_name value from the store config."""
        system = _build_system_with_store_config(
            _make_store_config("age", db_name="myPostgresDB")
        )
        self.assertEqual(system.store.db_name, "myPostgresDB")

    def test_age_store_uses_default_db_name_when_not_configured(self):
        """AGEDatabase must fall back to 'postgresDB' when db_name is absent."""
        store_cfg = _make_store_config("age")
        # Confirm the key is genuinely absent so the default path is taken.
        self.assertNotIn("db_name", store_cfg)
        system = _build_system_with_store_config(store_cfg)
        self.assertEqual(system.store.db_name, "postgresDB")

    def test_age_store_not_a_neo4j_instance(self):
        """AGEDatabase is not a Neo4jDatabase."""
        system = _build_system_with_store_config(_make_store_config("age"))
        self.assertNotIsInstance(system.store, Neo4jDatabase)

    # ------------------------------------------------------------------
    # Neo4jDatabase branch
    # ------------------------------------------------------------------

    def test_neo4j_store_created_when_type_is_neo4j(self):
        """System must create a Neo4jDatabase when store_config type is 'neo4j'."""
        system = _build_system_with_store_config(_make_store_config("neo4j"))
        self.assertIsInstance(system.store, Neo4jDatabase)

    def test_neo4j_store_created_for_unknown_type(self):
        """Neo4jDatabase is the else-branch default for any non-'age' type."""
        system = _build_system_with_store_config(_make_store_config("unknown_backend"))
        self.assertIsInstance(system.store, Neo4jDatabase)

    def test_neo4j_store_has_correct_name(self):
        """The Neo4jDatabase store name must match the configured store name."""
        system = _build_system_with_store_config(
            _make_store_config("neo4j", name="neo_graph")
        )
        self.assertEqual(system.store.name, "neo_graph")

    def test_neo4j_store_not_an_age_instance(self):
        """Neo4jDatabase is not an AGEDatabase."""
        system = _build_system_with_store_config(_make_store_config("neo4j"))
        self.assertNotIsInstance(system.store, AGEDatabase)

    # ------------------------------------------------------------------
    # Constructor mock-based verification
    # ------------------------------------------------------------------

    def test_age_constructor_called_with_correct_args(self):
        """
        When type is 'age', AGEDatabase must be called with the factory,
        name, db_name, uri, mode, log and jit arguments.
        """
        store_cfg = _make_store_config("age", db_name="myDB", name="rmtc_test")
        log = Logger()
        factory = ModuleFactory(log=log)
        config = _MockConfig(store_cfg)

        with patch("rmtc_core.AGEDatabase") as MockAGE:
            # The mock returns a MagicMock that satisfies store.broadcaster usage
            mock_store = MagicMock()
            MockAGE.return_value = mock_store

            System(
                config=config,
                log=log,
                factory=factory,
                tracker=MagicMock(),
                asset_manager=MagicMock(),
                env_manager=MagicMock(),
                broadcaster=Broadcaster(),
                objects=Objects(),
                mode=Mode.PRODUCTION,
            )

            MockAGE.assert_called_once()
            _, kwargs = MockAGE.call_args
            self.assertEqual(kwargs["name"], "rmtc_test")
            self.assertEqual(kwargs["db_name"], "myDB")
            self.assertIsInstance(kwargs["uri"], URI)
            self.assertEqual(kwargs["factory"], factory)

    def test_neo4j_constructor_called_with_correct_args(self):
        """
        When type is 'neo4j', Neo4jDatabase must be called with factory,
        name, uri, mode, log and jit arguments (no db_name).
        """
        store_cfg = _make_store_config("neo4j", name="rmtc_neo")
        log = Logger()
        factory = ModuleFactory(log=log)
        config = _MockConfig(store_cfg)

        with patch("rmtc_core.Neo4jDatabase") as MockNeo4j:
            mock_store = MagicMock()
            MockNeo4j.return_value = mock_store

            System(
                config=config,
                log=log,
                factory=factory,
                tracker=MagicMock(),
                asset_manager=MagicMock(),
                env_manager=MagicMock(),
                broadcaster=Broadcaster(),
                objects=Objects(),
                mode=Mode.PRODUCTION,
            )

            MockNeo4j.assert_called_once()
            _, kwargs = MockNeo4j.call_args
            self.assertEqual(kwargs["name"], "rmtc_neo")
            self.assertIsInstance(kwargs["uri"], URI)
            self.assertEqual(kwargs["factory"], factory)
            # Neo4jDatabase must NOT receive a db_name argument
            self.assertNotIn("db_name", kwargs)

    # ------------------------------------------------------------------
    # Pre-supplied store bypasses conditional logic
    # ------------------------------------------------------------------

    def test_provided_store_bypasses_config_selection(self):
        """
        When a store is passed directly to System, the config-based
        conditional selection must be skipped entirely.
        """
        pre_built_store = MagicMock()
        log = Logger()
        factory = ModuleFactory(log=log)
        # Even if config says 'age', a pre-built store takes precedence.
        config = _MockConfig(_make_store_config("age"))

        with patch("rmtc_core.AGEDatabase") as MockAGE, patch(
            "rmtc_core.Neo4jDatabase"
        ) as MockNeo4j:
            System(
                config=config,
                store=pre_built_store,
                log=log,
                factory=factory,
                tracker=MagicMock(),
                asset_manager=MagicMock(),
                env_manager=MagicMock(),
                broadcaster=Broadcaster(),
                objects=Objects(),
                mode=Mode.PRODUCTION,
            )

            MockAGE.assert_not_called()
            MockNeo4j.assert_not_called()

    # ------------------------------------------------------------------
    # Boundary / regression cases
    # ------------------------------------------------------------------

    def test_age_store_type_comparison_is_case_sensitive(self):
        """
        The type comparison 'age' is exact; 'AGE' or 'Age' must fall
        through to the Neo4jDatabase branch.
        """
        for variant in ("AGE", "Age", "aGe"):
            with self.subTest(variant=variant):
                system = _build_system_with_store_config(
                    _make_store_config(variant)
                )
                self.assertIsInstance(
                    system.store,
                    Neo4jDatabase,
                    msg=f"Expected Neo4jDatabase for type='{variant}' (case-sensitive check)",
                )

    def test_age_store_empty_db_name_uses_empty_string(self):
        """
        If db_name is explicitly set to an empty string in the config,
        that value (not the default) must be forwarded to AGEDatabase.
        """
        store_cfg = _make_store_config("age")
        store_cfg["db_name"] = ""
        system = _build_system_with_store_config(store_cfg)
        self.assertIsInstance(system.store, AGEDatabase)
        self.assertEqual(system.store.db_name, "")
