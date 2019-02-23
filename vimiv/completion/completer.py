# vim: ft=python fileencoding=utf-8 sw=4 et sts=4

# This file is part of vimiv.
# Copyright 2017-2019 Christian Karl (karlch) <karlch at protonmail dot com>
# License: GNU GPL v3, see the "LICENSE" and "AUTHORS" files for details.

"""Completer class as man-in-the-middle between command line and completion."""

from PyQt5.QtCore import QObject

from vimiv import api, utils
from vimiv.completion import completionmodels


class Completer(QObject):
    """Handle interaction between command line and completion.

    The commandline is stored as attribute, the completion widget is the parent
    class. Models are all created and dealt with depending on text in the
    command line.

    Attributes:
        _cmd: CommandLine object.
        _completion: CompletionWidget object.
        _proxy_model: The completion filter used.
    """

    @api.objreg.register
    def __init__(self, commandline, completion):
        super().__init__()
        self._proxy_model = None
        self._cmd = commandline
        self._completion = completion

        self._completion.activated.connect(self._on_completion)
        api.modes.signals.entered.connect(self._on_mode_entered)
        self._cmd.textEdited.connect(self._on_text_changed)
        self._cmd.editingFinished.connect(self._on_editing_finished)

    @property
    def proxy_model(self):
        return self._proxy_model

    @proxy_model.setter
    def proxy_model(self, proxy_model: api.completion.BaseFilter):
        self._proxy_model = proxy_model
        self._completion.setModel(proxy_model)

    @utils.slot
    def _on_mode_entered(self, mode: api.modes.Mode, last_mode: api.modes.Mode):
        """Initialize completion when command mode was entered.

        Args:
            mode: The mode entered.
            last_mode: The mode left.
        """
        if mode == api.modes.COMMAND:
            # Set model according to text, defaults are not possible as
            # :command accepts arbitrary text as argument
            self._maybe_update_model(self._cmd.text())
            self.proxy_model.sourceModel().on_enter(
                self.proxy_model.strip_text(self._cmd.text()), last_mode
            )
            # Show if the model is not empty
            self._maybe_show()
            self._completion.raise_()

    @utils.slot
    def _on_text_changed(self, text: str):
        """Update completions when text changed."""
        # Clear selection
        self._completion.selectionModel().clear()
        # Update model
        self._maybe_update_model(text)
        self.proxy_model.sourceModel().on_text_changed(
            self.proxy_model.strip_text(text)
        )
        # Refilter
        self.proxy_model.refilter(text)

    @utils.slot
    def _on_editing_finished(self):
        """Reset filter and hide completion widget."""
        self._completion.selectionModel().clear()
        self.proxy_model.reset()
        self._completion.hide()

    def _maybe_update_model(self, text):
        """Update model depending on text."""
        module = api.completion.get_module(text)
        self.proxy_model = module.Filter
        self.proxy_model.setSourceModel(module.Model)
        self._completion.update_column_widths()

    def _maybe_show(self):
        """Show completion widget if the model is not empty."""
        if not isinstance(self.proxy_model.sourceModel(), completionmodels.Empty):
            self._completion.show()

    @utils.slot
    def _on_completion(self, text: str):
        """Set commandline text when completion was activated.

        Args:
            text: Suggested text from completion.
        """
        # Get prefix and prepended digits
        cmdtext = self._cmd.text()
        prefix, cmdtext = cmdtext[0], cmdtext[1:]
        digits = ""
        while cmdtext and cmdtext[0].isdigit():
            digits += cmdtext[0]
            cmdtext = cmdtext[1:]
        # Set text in commandline
        self._cmd.setText(prefix + digits + text)


def instance():
    return api.objreg.get(Completer)
