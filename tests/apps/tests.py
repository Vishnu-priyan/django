from __future__ import absolute_import, unicode_literals

import os
import sys
from unittest import skipUnless

from django.apps import apps, AppConfig
from django.apps.registry import Apps
from django.contrib.admin.models import LogEntry
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.test import TestCase, override_settings
from django.test.utils import extend_sys_path
from django.utils._os import upath
from django.utils import six

from .default_config_app.apps import CustomConfig
from .models import (
    TotallyNormal, SoAlternative, new_apps,
    Relation, AbstractPerson, BasePerson, new_apps_2
)


# Small list with a variety of cases for tests that iterate on installed apps.
# Intentionally not in alphabetical order to check if the order is preserved.

SOME_INSTALLED_APPS = [
    'apps.apps.MyAdmin',
    'apps.apps.MyAuth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

SOME_INSTALLED_APPS_NAMES = [
    'django.contrib.admin',
    'django.contrib.auth',
] + SOME_INSTALLED_APPS[2:]

HERE = os.path.dirname(__file__)


class AppsTests(TestCase):

    def test_singleton_master(self):
        """
        Ensures that only one master registry can exist.
        """
        with self.assertRaises(RuntimeError):
            Apps(installed_apps=None)

    def test_ready(self):
        """
        Tests the ready property of the master registry.
        """
        # The master app registry is always ready when the tests run.
        self.assertTrue(apps.ready)
        # Non-master app registries are populated in __init__.
        self.assertTrue(Apps().ready)

    def test_bad_app_config(self):
        """
        Tests when INSTALLED_APPS contains an incorrect app config.
        """
        with self.assertRaises(ImproperlyConfigured):
            with self.settings(INSTALLED_APPS=['apps.apps.BadConfig']):
                pass

    def test_not_an_app_config(self):
        """
        Tests when INSTALLED_APPS contains a class that isn't an app config.
        """
        with self.assertRaises(ImproperlyConfigured):
            with self.settings(INSTALLED_APPS=['apps.apps.NotAConfig']):
                pass

    def test_no_such_app(self):
        """
        Tests when INSTALLED_APPS contains an app that doesn't exist, either
        directly or via an app config.
        """
        with self.assertRaises(ImportError):
            with self.settings(INSTALLED_APPS=['there is no such app']):
                pass
        with self.assertRaises(ImportError):
            with self.settings(INSTALLED_APPS=['apps.apps.NoSuchApp']):
                pass

    def test_no_such_app_config(self):
        """
        Tests when INSTALLED_APPS contains an entry that doesn't exist.
        """
        with self.assertRaises(ImportError):
            with self.settings(INSTALLED_APPS=['apps.apps.NoSuchConfig']):
                pass

    def test_default_app_config(self):
        with self.settings(INSTALLED_APPS=['apps.default_config_app']):
            config = apps.get_app_config('default_config_app')
        self.assertIsInstance(config, CustomConfig)

    @override_settings(INSTALLED_APPS=SOME_INSTALLED_APPS)
    def test_get_app_configs(self):
        """
        Tests apps.get_app_configs().
        """
        app_configs = apps.get_app_configs()
        self.assertListEqual(
            [app_config.name for app_config in app_configs],
            SOME_INSTALLED_APPS_NAMES)

    @override_settings(INSTALLED_APPS=SOME_INSTALLED_APPS)
    def test_get_app_config(self):
        """
        Tests apps.get_app_config().
        """
        app_config = apps.get_app_config('admin')
        self.assertEqual(app_config.name, 'django.contrib.admin')

        app_config = apps.get_app_config('staticfiles')
        self.assertEqual(app_config.name, 'django.contrib.staticfiles')

        with self.assertRaises(LookupError):
            apps.get_app_config('webdesign')

    @override_settings(INSTALLED_APPS=SOME_INSTALLED_APPS)
    def test_is_installed(self):
        """
        Tests apps.is_installed().
        """
        self.assertTrue(apps.is_installed('django.contrib.admin'))
        self.assertTrue(apps.is_installed('django.contrib.auth'))
        self.assertTrue(apps.is_installed('django.contrib.staticfiles'))
        self.assertFalse(apps.is_installed('django.contrib.webdesign'))

    @override_settings(INSTALLED_APPS=SOME_INSTALLED_APPS)
    def test_get_model(self):
        """
        Tests apps.get_model().
        """
        self.assertEqual(apps.get_model('admin', 'LogEntry'), LogEntry)
        with self.assertRaises(LookupError):
            apps.get_model('admin', 'LogExit')

        # App label is case-sensitive, Model name is case-insensitive.
        self.assertEqual(apps.get_model('admin', 'loGentrY'), LogEntry)
        with self.assertRaises(LookupError):
            apps.get_model('Admin', 'LogEntry')

        # A single argument is accepted.
        self.assertEqual(apps.get_model('admin.LogEntry'), LogEntry)
        with self.assertRaises(LookupError):
            apps.get_model('admin.LogExit')
        with self.assertRaises(ValueError):
            apps.get_model('admin_LogEntry')

    @override_settings(INSTALLED_APPS=['apps.apps.RelabeledAppsConfig'])
    def test_relabeling(self):
        self.assertEqual(apps.get_app_config('relabeled').name, 'apps')

    def test_duplicate_labels(self):
        with six.assertRaisesRegex(self, ImproperlyConfigured, "Application labels aren't unique"):
            with self.settings(INSTALLED_APPS=['apps.apps.PlainAppsConfig', 'apps']):
                pass

    def test_duplicate_names(self):
        with six.assertRaisesRegex(self, ImproperlyConfigured, "Application names aren't unique"):
            with self.settings(INSTALLED_APPS=['apps.apps.RelabeledAppsConfig', 'apps']):
                pass

    def test_models_py(self):
        """
        Tests that the models in the models.py file were loaded correctly.
        """
        self.assertEqual(apps.get_model("apps", "TotallyNormal"), TotallyNormal)
        with self.assertRaises(LookupError):
            apps.get_model("apps", "SoAlternative")

        with self.assertRaises(LookupError):
            new_apps.get_model("apps", "TotallyNormal")
        self.assertEqual(new_apps.get_model("apps", "SoAlternative"), SoAlternative)

    def test_dynamic_load(self):
        """
        Makes a new model at runtime and ensures it goes into the right place.
        """
        old_models = list(apps.get_app_config("apps").get_models())
        # Construct a new model in a new app registry
        body = {}
        new_apps = Apps(["apps"])
        meta_contents = {
            'app_label': "apps",
            'apps': new_apps,
        }
        meta = type(str("Meta"), tuple(), meta_contents)
        body['Meta'] = meta
        body['__module__'] = TotallyNormal.__module__
        temp_model = type(str("SouthPonies"), (models.Model,), body)
        # Make sure it appeared in the right place!
        self.assertListEqual(list(apps.get_app_config("apps").get_models()), old_models)
        with self.assertRaises(LookupError):
            apps.get_model("apps", "SouthPonies")
        self.assertEqual(new_apps.get_model("apps", "SouthPonies"), temp_model)


class Stub(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class AppConfigTests(TestCase):
    """Unit tests for AppConfig class."""
    def test_path_set_explicitly(self):
        """If subclass sets path as class attr, no module attributes needed."""
        class MyAppConfig(AppConfig):
            path = 'foo'

        ac = MyAppConfig('label', Stub())

        self.assertEqual(ac.path, 'foo')

    def test_explicit_path_overrides(self):
        """If path set as class attr, overrides __path__ and __file__."""
        class MyAppConfig(AppConfig):
            path = 'foo'

        ac = MyAppConfig('label', Stub(__path__=['a'], __file__='b/__init__.py'))

        self.assertEqual(ac.path, 'foo')

    def test_dunder_path(self):
        """If single element in __path__, use it (in preference to __file__)."""
        ac = AppConfig('label', Stub(__path__=['a'], __file__='b/__init__.py'))

        self.assertEqual(ac.path, 'a')

    def test_no_dunder_path_fallback_to_dunder_file(self):
        """If there is no __path__ attr, use __file__."""
        ac = AppConfig('label', Stub(__file__='b/__init__.py'))

        self.assertEqual(ac.path, 'b')

    def test_empty_dunder_path_fallback_to_dunder_file(self):
        """If the __path__ attr is empty, use __file__ if set."""
        ac = AppConfig('label', Stub(__path__=[], __file__='b/__init__.py'))

        self.assertEqual(ac.path, 'b')

    def test_multiple_dunder_path_fallback_to_dunder_file(self):
        """If the __path__ attr is length>1, use __file__ if set."""
        ac = AppConfig('label', Stub(__path__=['a', 'b'], __file__='c/__init__.py'))

        self.assertEqual(ac.path, 'c')

    def test_no_dunder_path_or_dunder_file(self):
        """If there is no __path__ or __file__, raise ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured):
            AppConfig('label', Stub())

    def test_empty_dunder_path_no_dunder_file(self):
        """If the __path__ attr is empty and there is no __file__, raise."""
        with self.assertRaises(ImproperlyConfigured):
            AppConfig('label', Stub(__path__=[]))

    def test_multiple_dunder_path_no_dunder_file(self):
        """If the __path__ attr is length>1 and there is no __file__, raise."""
        with self.assertRaises(ImproperlyConfigured):
            AppConfig('label', Stub(__path__=['a', 'b']))


@skipUnless(
    sys.version_info > (3, 3, 0),
    "Namespace packages sans __init__.py were added in Python 3.3")
class NamespacePackageAppTests(TestCase):
    # We need nsapp to be top-level so our multiple-paths tests can add another
    # location for it (if its inside a normal package with an __init__.py that
    # isn't possible). In order to avoid cluttering the already-full tests/ dir
    # (which is on sys.path), we add these new entries to sys.path temporarily.
    base_location = os.path.join(HERE, 'namespace_package_base')
    other_location = os.path.join(HERE, 'namespace_package_other_base')
    app_path = os.path.join(base_location, 'nsapp')

    def test_single_path(self):
        """
        A Py3.3+ namespace package can be an app if it has only one path.
        """
        with extend_sys_path(self.base_location):
            with self.settings(INSTALLED_APPS=['nsapp']):
                app_config = apps.get_app_config('nsapp')
                self.assertEqual(app_config.path, upath(self.app_path))

    def test_multiple_paths(self):
        """
        A Py3.3+ namespace package with multiple locations cannot be an app.

        (Because then we wouldn't know where to load its templates, static
        assets, etc from.)

        """
        # Temporarily add two directories to sys.path that both contain
        # components of the "nsapp" package.
        with extend_sys_path(self.base_location, self.other_location):
            with self.assertRaises(ImproperlyConfigured):
                with self.settings(INSTALLED_APPS=['nsapp']):
                    pass

    def test_multiple_paths_explicit_path(self):
        """
        Multiple locations are ok only if app-config has explicit path.
        """
        # Temporarily add two directories to sys.path that both contain
        # components of the "nsapp" package.
        with extend_sys_path(self.base_location, self.other_location):
            with self.settings(INSTALLED_APPS=['nsapp.apps.NSAppConfig']):
                app_config = apps.get_app_config('nsapp')
                self.assertEqual(app_config.path, upath(self.app_path))


class AppRelationsTest(TestCase):

    def test_relations_related_objects(self):
        tree, _ = new_apps_2.related_objects_relation_graph
        self.assertEquals(
            [field.related_query_name() for field in tree[Relation._meta]],
            [u'BasePerson_m2m_base+', u'BasePerson_m2m_abstract+', u'fk_base_rel', u'fo_base_rel']
        )
        self.assertEquals(
            [field.related_query_name() for field in tree[BasePerson._meta]],
            [u'BasePerson_friends_base+', u'BasePerson_friends_base+', u'BasePerson_m2m_base+',
             u'BasePerson_following_base+', u'BasePerson_following_base+', u'BasePerson_m2m_abstract+',
             u'BasePerson_friends_abstract+', u'BasePerson_friends_abstract+', u'BasePerson_following_abstract+',
             u'BasePerson_following_abstract+']
        )
        self.assertEquals([field.related_query_name() for field in tree[AbstractPerson._meta]], [])

    def test_relations_proxy_objects(self):
        _, proxy_tree = new_apps_2.related_objects_relation_graph
        self.assertEquals(
            [field.related_query_name() for field in proxy_tree[Relation]],
            [u'fk_to_proxy']
        )

    def test_relations_related_m2m(self):
        tree = new_apps_2.related_m2m_relation_graph
        self.assertEquals(
            [field.related_query_name() for field in tree[Relation._meta]],
            [u'm2m_abstract_rel', u'm2m_base_rel']
        )
        self.assertEquals(
            [field.related_query_name() for field in tree[BasePerson._meta]],
            [u'friends_abstract_rel_+', u'followers_abstract', u'friends_base_rel_+',
             u'followers_base']
        )
        self.assertEquals([field.related_query_name() for field in tree[AbstractPerson._meta]], [])
