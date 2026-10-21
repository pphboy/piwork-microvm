#!/usr/bin/env python3
"""Acceptance-only AT-SPI driver for the Linux launcher.

The WebKitGTK content exposes its DOM through AT-SPI, so buttons can be invoked
without moving the desktop pointer. Test tooling only.
"""
import sys
import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi  # noqa: E402


def app_node():
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        try:
            if 'piwork' in (app.get_name() or '').lower():
                return app
        except Exception:
            pass
    raise SystemExit('launcher application not found')


def walk(node, depth=0, limit=14):
    if depth > limit:
        return
    try:
        print('  ' * depth, node.get_role_name(), repr(node.get_name() or ''))
        for i in range(node.get_child_count()):
            walk(node.get_child_at_index(i), depth + 1, limit)
    except Exception:
        pass


def find(node, name, exact=True):
    try:
        value = node.get_name() or ''
        if (value == name) if exact else (name in value):
            return node
    except Exception:
        pass
    try:
        for i in range(node.get_child_count()):
            found = find(node.get_child_at_index(i), name, exact)
            if found:
                return found
    except Exception:
        pass
    return None


def find_role(node, role, name):
    try:
        if (node.get_role_name() or '') == role and name in (node.get_name() or ''):
            return node
    except Exception:
        pass
    try:
        for i in range(node.get_child_count()):
            found = find_role(node.get_child_at_index(i), role, name)
            if found:
                return found
    except Exception:
        pass
    return None


def click(name, role=None):
    node = find_role(app_node(), role, name) if role else find(app_node(), name, exact=False)
    if not node:
        raise SystemExit(f'node not found: {name}')
    print('role', node.get_role_name(), 'name', repr(node.get_name()), 'actions', node.get_n_actions())
    if node.get_n_actions() < 1:
        raise SystemExit('node has no action')
    print('action', node.get_action_name(0), 'result', node.do_action(0))


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'tree'
    if command == 'tree':
        walk(app_node())
    elif command == 'click':
        click(sys.argv[2])
    elif command == 'click-button':
        click(sys.argv[2], 'button')
    elif command == 'find':
        node = find(app_node(), sys.argv[2], exact=False)
        if not node:
            raise SystemExit('not found')
        print(node.get_role_name(), repr(node.get_name()), 'actions', node.get_n_actions())
    else:
        raise SystemExit('usage: atspi_ui.py tree|click NAME|click-button NAME|find NAME')


if __name__ == '__main__':
    main()
