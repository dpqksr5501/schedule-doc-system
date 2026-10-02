"""Explicit bridge allowlist for the pinned pywebview backend.

The vendor dispatch can resolve dotted Python attributes. Never let a web
message reach that fallback, even if a future UI accidentally introduces XSS.
"""
import logging
import re

API_METHODS = ('bootstrap', 'ready', 'save_persistent_data', 'restore_data', 'preview_restore',
               'backup_data', 'list_backups', 'get_backup', 'preview_document', 'export_document', 'export_csv',
               'open_export_folder', 'open_last_output', 'open_manual', 'check_update',
               'apply_update', 'set_editing')


def guard_dispatch(original):
    def dispatch(window, func_name, param, value_id):
        if not isinstance(value_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value_id):
            logging.warning('Rejected malformed bridge callback')
            return
        if func_name == 'pywebviewAsyncCallback':
            if value_id not in window._callbacks:
                return
        elif func_name not in API_METHODS or func_name not in window._functions:
            logging.warning('Rejected unlisted bridge method')
            return
        return original(window, func_name, param, value_id)
    return dispatch


def expose(window, api):
    import webview.util
    # Install before webview.start imports the Edge backend's dispatch alias.
    webview.util.js_bridge_call = guard_dispatch(webview.util.js_bridge_call)
    window.expose(*(getattr(api, name) for name in API_METHODS))
