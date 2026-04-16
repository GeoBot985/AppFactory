import unittest
import os
import sys
from pathlib import Path
from Demo10.runtime_profiles.models import (
    RuntimeProfile, InterpreterConfig, InterpreterMode,
    EnvConfig, EnvInheritMode, CommandPolicy
)
from Demo10.runtime_profiles.registry import ProfileRegistry
from Demo10.runtime_profiles.interpreter import InterpreterResolver, InterpreterValidator
from Demo10.runtime_profiles.environment import EnvironmentBuilder, EnvironmentMasker
from Demo10.runtime_profiles.commands import CommandExecutor

class TestSpec015Runtime(unittest.TestCase):
    def test_profile_registry(self):
        registry = ProfileRegistry()
        default = registry.get_profile("default")
        self.assertIsNotNone(default)
        self.assertEqual(default.profile_id, "default")

    def test_interpreter_resolution(self):
        resolver = InterpreterResolver(Path.cwd())
        profile = RuntimeProfile(
            profile_id="test",
            interpreter=InterpreterConfig(mode=InterpreterMode.PATH, value=sys.executable)
        )
        resolved = resolver.resolve(profile)
        self.assertEqual(resolved, sys.executable)

    def test_interpreter_validation(self):
        validator = InterpreterValidator()
        ok, err_type, version = validator.validate(sys.executable)
        self.assertTrue(ok)
        self.assertEqual(err_type, "SUCCESS")
        self.assertIn("Python", version)

    def test_environment_builder(self):
        builder = EnvironmentBuilder()
        profile = RuntimeProfile(
            profile_id="test",
            env=EnvConfig(
                inherit_mode=EnvInheritMode.MINIMAL,
                inject={"TEST_VAR": "test_value"}
            )
        )
        env = builder.build(profile)
        self.assertIn("PATH", env)
        self.assertEqual(env["TEST_VAR"], "test_value")

    def test_environment_masker(self):
        masker = EnvironmentMasker()
        env = {"API_KEY": "secret123", "PORT": "8080"}
        masked = masker.mask_env(env)
        self.assertEqual(masked["API_KEY"], "***MASKED***")
        self.assertEqual(masked["PORT"], "8080")

    def test_command_executor(self):
        profile = RuntimeProfile(
            profile_id="test",
            command_policy=CommandPolicy(shell=False)
        )
        executor = CommandExecutor(profile, sys.executable, {}, Path.cwd())

        # Run a simple python command
        res = executor.run([sys.executable, "-c", "print('hello')"])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.stdout.strip(), "hello")

    def test_command_denylist(self):
        profile = RuntimeProfile(
            profile_id="test",
            command_policy=CommandPolicy(deny_commands=["forbidden"])
        )
        executor = CommandExecutor(profile, sys.executable, {}, Path.cwd())
        res = executor.run(["forbidden", "args"])
        self.assertEqual(res.exit_code, -1)
        self.assertIn("COMMAND_NOT_ALLOWED", res.stderr)

if __name__ == "__main__":
    unittest.main()
