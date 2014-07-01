from __future__ import unicode_literals

from django.db import router
from django.db.models.fields import NOT_PROVIDED
from django.utils import six
from .base import Operation


class AddField(Operation):
    """
    Adds a field to a model.
    """

    def __init__(self, model_name, name, field, preserve_default=True):
        self.model_name = model_name
        self.name = name
        self.field = field
        self.preserve_default = preserve_default

    def state_forwards(self, app_label, state):
        # If preserve default is off, don't use the default for future state
        if not self.preserve_default:
            field = self.field.clone()
            field.default = NOT_PROVIDED
        else:
            field = self.field
        state.models[app_label, self.model_name.lower()].fields.append((self.name, field))

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        to_model = to_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, to_model):
            field = to_model._meta.get_new_field(self.name, True)
            if not self.preserve_default:
                field.default = self.field.default
            schema_editor.add_field(
                from_model,
                field,
            )
            if not self.preserve_default:
                field.default = NOT_PROVIDED

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, from_model):
            schema_editor.remove_field(from_model, from_model._meta.get_new_field(self.name, True))

    def describe(self):
        return "Add field %s to %s" % (self.name, self.model_name)

    def __eq__(self, other):
        return (
            (self.__class__ == other.__class__) and
            (self.name == other.name) and
            (self.model_name.lower() == other.model_name.lower()) and
            (self.field.deconstruct()[1:] == other.field.deconstruct()[1:])
        )

    def references_model(self, name, app_label=None):
        return name.lower() == self.model_name.lower()

    def references_field(self, model_name, name, app_label=None):
        return self.references_model(model_name) and name.lower() == self.name.lower()


class RemoveField(Operation):
    """
    Removes a field from a model.
    """

    def __init__(self, model_name, name):
        self.model_name = model_name
        self.name = name

    def state_forwards(self, app_label, state):
        new_fields = []
        for name, instance in state.models[app_label, self.model_name.lower()].fields:
            if name != self.name:
                new_fields.append((name, instance))
        state.models[app_label, self.model_name.lower()].fields = new_fields

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, from_model):
            schema_editor.remove_field(from_model, from_model._meta.get_new_field(self.name, True))

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        to_model = to_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, to_model):
            schema_editor.add_field(from_model, to_model._meta.get_new_field(self.name, True))

    def describe(self):
        return "Remove field %s from %s" % (self.name, self.model_name)

    def references_model(self, name, app_label=None):
        return name.lower() == self.model_name.lower()

    def references_field(self, model_name, name, app_label=None):
        return self.references_model(model_name) and name.lower() == self.name.lower()


class AlterField(Operation):
    """
    Alters a field's database column (e.g. null, max_length) to the provided new field
    """

    def __init__(self, model_name, name, field):
        self.model_name = model_name
        self.name = name
        self.field = field

    def state_forwards(self, app_label, state):
        state.models[app_label, self.model_name.lower()].fields = [
            (n, self.field if n == self.name else f) for n, f in state.models[app_label, self.model_name.lower()].fields
        ]

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        to_model = to_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, to_model):
            from_field = from_model._meta.get_new_field(self.name, True)
            to_field = to_model._meta.get_new_field(self.name, True)
            # If the field is a relatedfield with an unresolved rel.to, just
            # set it equal to the other field side. Bandaid fix for AlterField
            # migrations that are part of a RenameModel change.
            if from_field.rel and from_field.rel.to:
                if isinstance(from_field.rel.to, six.string_types):
                    from_field.rel.to = to_field.rel.to
                elif isinstance(to_field.rel.to, six.string_types):
                    to_field.rel.to = from_field.rel.to
            schema_editor.alter_field(from_model, from_field, to_field)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        self.database_forwards(app_label, schema_editor, from_state, to_state)

    def describe(self):
        return "Alter field %s on %s" % (self.name, self.model_name)

    def __eq__(self, other):
        return (
            (self.__class__ == other.__class__) and
            (self.name == other.name) and
            (self.model_name.lower() == other.model_name.lower()) and
            (self.field.deconstruct()[1:] == other.field.deconstruct()[1:])
        )

    def references_model(self, name, app_label=None):
        return name.lower() == self.model_name.lower()

    def references_field(self, model_name, name, app_label=None):
        return self.references_model(model_name) and name.lower() == self.name.lower()


class RenameField(Operation):
    """
    Renames a field on the model. Might affect db_column too.
    """

    def __init__(self, model_name, old_name, new_name):
        self.model_name = model_name
        self.old_name = old_name
        self.new_name = new_name

    def state_forwards(self, app_label, state):
        state.models[app_label, self.model_name.lower()].fields = [
            (self.new_name if n == self.old_name else n, f) for n, f in state.models[app_label, self.model_name.lower()].fields
        ]

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        to_model = to_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, to_model):
            schema_editor.alter_field(
                from_model,
                from_model._meta.get_new_field(self.old_name, True),
                to_model._meta.get_new_field(self.new_name, True),
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        from_model = from_state.render().get_model(app_label, self.model_name)
        to_model = to_state.render().get_model(app_label, self.model_name)
        if router.allow_migrate(schema_editor.connection.alias, to_model):
            schema_editor.alter_field(
                from_model,
                from_model._meta.get_new_field(self.new_name, True),
                to_model._meta.get_new_field(self.old_name, True),
            )

    def describe(self):
        return "Rename field %s on %s to %s" % (self.old_name, self.model_name, self.new_name)

    def references_model(self, name, app_label=None):
        return name.lower() == self.model_name.lower()

    def references_field(self, model_name, name, app_label=None):
        return self.references_model(model_name) and (
            name.lower() == self.old_name.lower() or
            name.lower() == self.new_name.lower()
        )
