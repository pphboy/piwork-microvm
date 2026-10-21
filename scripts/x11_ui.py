#!/usr/bin/env python3
"""Acceptance-only X11/XTest helper for the Linux WSLg desktop.

This is test tooling, not part of the shipped launcher. It drives the real
WebKitGTK window and native GTK dialogs through X11 so acceptance does not
depend on the Windows z-order or pointer scaling.
"""
import ctypes
import ctypes.util
import sys

X11 = ctypes.CDLL(ctypes.util.find_library('X11'))
XTST = ctypes.CDLL(ctypes.util.find_library('Xtst'))
X11.XOpenDisplay.restype = ctypes.c_void_p
X11.XOpenDisplay.argtypes = [ctypes.c_char_p]


class Rect(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int),
                ('width', ctypes.c_int), ('height', ctypes.c_int),
                ('border_width', ctypes.c_int), ('depth', ctypes.c_int),
                ('visual', ctypes.c_void_p), ('root', ctypes.c_ulong),
                ('class_', ctypes.c_int), ('bit_gravity', ctypes.c_int),
                ('win_gravity', ctypes.c_int), ('backing_store', ctypes.c_int),
                ('backing_planes', ctypes.c_ulong), ('backing_pixel', ctypes.c_ulong),
                ('save_under', ctypes.c_int), ('colormap', ctypes.c_ulong),
                ('map_installed', ctypes.c_int), ('map_state', ctypes.c_int),
                ('all_event_masks', ctypes.c_long), ('your_event_mask', ctypes.c_long),
                ('do_not_propagate_mask', ctypes.c_long),
                ('override_redirect', ctypes.c_int), ('screen', ctypes.c_void_p)]


class WindowAttributes(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int), ('y', ctypes.c_int),
                ('width', ctypes.c_int), ('height', ctypes.c_int),
                ('border_width', ctypes.c_int), ('depth', ctypes.c_int),
                ('visual', ctypes.c_void_p), ('root', ctypes.c_ulong),
                ('class_', ctypes.c_int), ('bit_gravity', ctypes.c_int),
                ('win_gravity', ctypes.c_int), ('backing_store', ctypes.c_int),
                ('backing_planes', ctypes.c_ulong), ('backing_pixel', ctypes.c_ulong),
                ('save_under', ctypes.c_int), ('colormap', ctypes.c_ulong),
                ('map_installed', ctypes.c_int), ('map_state', ctypes.c_int),
                ('all_event_masks', ctypes.c_long), ('your_event_mask', ctypes.c_long),
                ('do_not_propagate_mask', ctypes.c_long),
                ('override_redirect', ctypes.c_int), ('screen', ctypes.c_void_p)]


X11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
X11.XDefaultRootWindow.restype = ctypes.c_ulong
X11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                           ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                           ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                           ctypes.POINTER(ctypes.c_uint)]
X11.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]
X11.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(WindowAttributes)]
X11.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
X11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
X11.XMoveResizeWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
X11.XTranslateCoordinates.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                      ctypes.c_int, ctypes.c_int,
                                      ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                                      ctypes.POINTER(ctypes.c_ulong)]
X11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
X11.XKeysymToKeycode.restype = ctypes.c_ubyte
X11.XFlush.argtypes = [ctypes.c_void_p]
X11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
XTST.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_ulong]
XTST.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
XTST.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]


def display(name=':0'):
    d = X11.XOpenDisplay(name.encode())
    if not d:
        raise RuntimeError(f'cannot open X display {name}')
    return d


def _name(d, win):
    p = ctypes.c_char_p()
    if X11.XFetchName(d, win, ctypes.byref(p)) and p.value:
        return p.value.decode('utf-8', 'replace')
    return ''


def windows(d):
    root = X11.XDefaultRootWindow(d)
    result = []
    stack = [root]
    while stack:
        win = stack.pop()
        r, p = ctypes.c_ulong(), ctypes.c_ulong()
        children = ctypes.POINTER(ctypes.c_ulong)()
        n = ctypes.c_uint()
        if not X11.XQueryTree(d, win, ctypes.byref(r), ctypes.byref(p),
                              ctypes.byref(children), ctypes.byref(n)):
            continue
        for i in range(n.value):
            child = children[i]
            stack.append(child)
            attrs = WindowAttributes()
            if not X11.XGetWindowAttributes(d, child, ctypes.byref(attrs)):
                continue
            name = _name(d, child)
            if name:
                x, y = ctypes.c_int(), ctypes.c_int()
                root_ret = ctypes.c_ulong()
                X11.XTranslateCoordinates(d, child, root, 0, 0,
                                          ctypes.byref(x), ctypes.byref(y), ctypes.byref(root_ret))
                result.append({'id': child, 'name': name, 'x': x.value, 'y': y.value,
                               'w': attrs.width, 'h': attrs.height,
                               'mapped': attrs.map_state == 2})
    return result


def find(d, substring):
    matches = [w for w in windows(d) if substring.lower() in w['name'].lower()]
    return matches[-1] if matches else None


def focus(d, win):
    X11.XRaiseWindow(d, win['id'])
    X11.XSetInputFocus(d, win['id'], 1, 0)  # RevertToPointerRoot, CurrentTime
    X11.XSync(d, 0)


def move_resize(d, win, x, y, w, h):
    X11.XMoveResizeWindow(d, win['id'], x, y, w, h)
    X11.XSync(d, 0)


def click(d, x, y, button=1):
    XTST.XTestFakeMotionEvent(d, -1, x, y, 0)
    XTST.XTestFakeButtonEvent(d, button, 1, 0)
    XTST.XTestFakeButtonEvent(d, button, 0, 0)
    X11.XSync(d, 0)


def click_window(d, win, relx, rely, button=1):
    click(d, win['x'] + relx, win['y'] + rely, button)


KEYSYMS = {
    'return': 0xff0d, 'escape': 0xff1b, 'ctrl': 0xffe3, 'shift': 0xffe1,
    'tab': 0xff09, 'backspace': 0xff08, 'delete': 0xffff, 'l': 0x6c,
    'v': 0x76, 'a': 0x61, 'y': 0x79, 'n': 0x6e,
}


def key(d, keysym, down=True):
    code = X11.XKeysymToKeycode(d, keysym)
    XTST.XTestFakeKeyEvent(d, code, 1 if down else 0, 0)
    X11.XSync(d, 0)


def press(d, name, ctrl=False):
    if ctrl:
        key(d, KEYSYMS['ctrl'], True)
    ks = KEYSYMS[name] if name in KEYSYMS else ord(name)
    key(d, ks, True)
    key(d, ks, False)
    if ctrl:
        key(d, KEYSYMS['ctrl'], False)


def type_ascii(d, text):
    for ch in text:
        if ch == '/':
            ks = 0x2f
        elif ch == '-':
            ks = 0x2d
        elif ch == '.':
            ks = 0x2e
        elif ch == '_':
            key(d, KEYSYMS['shift'], True)
            key(d, 0x2d, True)
            key(d, 0x2d, False)
            key(d, KEYSYMS['shift'], False)
            continue
        elif ch == ' ':
            ks = 0x20
        else:
            ks = ord(ch)
        key(d, ks, True)
        key(d, ks, False)


def main():
    d = display()
    args = sys.argv[1:]
    if not args or args[0] == 'list':
        for w in windows(d):
            if w['mapped'] and (w['name'] or (len(args) > 1 and args[1] == 'all' and w['w'] > 100 and w['h'] > 100)):
                print(f"{w['id']} [{w['x']},{w['y']},{w['w']},{w['h']}] {w['name']}")
        return
    if args[0] == 'find':
        print(find(d, args[1]))
        return
    win = find(d, args[1]) if len(args) > 1 else None
    if args[0] in ('focus', 'clickrel', 'key', 'type', 'move') and not win:
        raise SystemExit(f'window not found: {args[1]}')
    if args[0] == 'focus':
        focus(d, win)
    elif args[0] == 'clickrel':
        focus(d, win)
        click_window(d, win, int(args[2]), int(args[3]))
    elif args[0] == 'click':
        click(d, int(args[1]), int(args[2]))
    elif args[0] == 'move':
        move_resize(d, win, int(args[2]), int(args[3]), int(args[4]), int(args[5]))
    elif args[0] == 'key':
        focus(d, win)
        for combo in args[2].split('+'):
            if not combo:
                continue
            parts = combo.split(':')
            if len(parts) == 2:
                press(d, parts[1], ctrl=parts[0] == 'ctrl')
            else:
                press(d, combo)
    elif args[0] == 'type':
        focus(d, win)
        type_ascii(d, args[2])
    else:
        raise SystemExit('usage: x11_ui.py list|find NAME|focus NAME|clickrel NAME X Y|move NAME X Y W H|key NAME combo|type NAME TEXT')


if __name__ == '__main__':
    main()
