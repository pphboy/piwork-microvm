#!/usr/bin/env python3
"""Inspect an isolated real X11/XWayland launcher without starting its VM.

Acceptance dependencies: Python GI (Gdk/GdkX11), Pillow, libX11 and libXtst.
Only the owned PID's window is inspected and closed.
"""
import argparse
import ctypes as c
import ctypes.util
import json
import os
import pathlib
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', required=True)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    root.mkdir(exist_ok=False)
    for name in ('config', 'data', 'cache', 'evidence'):
        (root / name).mkdir()
    os.environ['GDK_BACKEND'] = 'x11'
    import gi
    gi.require_version('Gdk', '3.0')
    gi.require_version('GdkX11', '3.0')
    from gi.repository import Gdk, GdkX11
    from PIL import Image
    pointer, word = c.c_void_p, c.c_ulong
    x = c.CDLL(ctypes.util.find_library('X11'))
    signatures = {
        'XOpenDisplay': ([c.c_char_p], pointer),
        'XDefaultRootWindow': ([pointer], word),
        'XQueryTree': ([pointer, word, c.POINTER(word), c.POINTER(word), c.POINTER(c.POINTER(word)), c.POINTER(c.c_uint)], c.c_int),
        'XInternAtom': ([pointer, c.c_char_p, c.c_int], word),
        'XGetWindowProperty': ([pointer, word, word, c.c_long, c.c_long, c.c_int, word, c.POINTER(word), c.POINTER(c.c_int), c.POINTER(word), c.POINTER(word), c.POINTER(c.POINTER(c.c_ubyte))], c.c_int),
        'XFree': ([pointer], c.c_int),
        'XRaiseWindow': ([pointer, word], c.c_int),
        'XMapWindow': ([pointer, word], c.c_int),
        'XFlush': ([pointer], c.c_int),
        'XGetGeometry': ([pointer, word, c.POINTER(word), c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(c.c_uint), c.POINTER(c.c_uint), c.POINTER(c.c_uint), c.POINTER(c.c_uint)], c.c_int),
        'XTranslateCoordinates': ([pointer, word, word, c.c_int, c.c_int, c.POINTER(c.c_int), c.POINTER(c.c_int), c.POINTER(word)], c.c_int),
        'XGetImage': ([pointer, word, c.c_int, c.c_int, c.c_uint, c.c_uint, word, c.c_int], pointer),
        'XGetPixel': ([pointer, c.c_int, c.c_int], word),
        'XDestroyImage': ([pointer], c.c_int),
        'XCloseDisplay': ([pointer], c.c_int),
    }
    for name, (parameters, result) in signatures.items():
        getattr(x, name).argtypes = parameters
        getattr(x, name).restype = result
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('X11 display unavailable')
    desktop = x.XDefaultRootWindow(display)
    xt = c.CDLL(ctypes.util.find_library('Xtst'))
    xt.XTestFakeMotionEvent.argtypes = [pointer, c.c_int, c.c_int, c.c_int, word]
    xt.XTestFakeButtonEvent.argtypes = [pointer, c.c_uint, c.c_int, word]

    def prop(window, name):
        data = c.POINTER(c.c_ubyte)()
        kind, count, remaining, fmt = word(), word(), word(), c.c_int()
        x.XGetWindowProperty(display, window, x.XInternAtom(display, name.encode(), False), 0, 5000000, False, 0,
                             c.byref(kind), c.byref(fmt), c.byref(count), c.byref(remaining), c.byref(data))
        if not data:
            return []
        result = list(c.cast(data, c.POINTER(word))[:count.value]) if fmt.value == 32 else c.string_at(data, count.value).decode(errors='replace')
        x.XFree(data)
        return result

    def descendants(window):
        owner, parent, count, children = word(), word(), c.c_uint(), c.POINTER(word)()
        x.XQueryTree(display, window, c.byref(owner), c.byref(parent), c.byref(children), c.byref(count))
        values = list(children[:count.value])
        if children:
            x.XFree(children)
        for child in values:
            yield child
            yield from descendants(child)

    def geometry(window):
        owner, px, py, width, height, border, depth = word(), c.c_int(), c.c_int(), c.c_uint(), c.c_uint(), c.c_uint(), c.c_uint()
        x.XGetGeometry(display, window, c.byref(owner), c.byref(px), c.byref(py), c.byref(width), c.byref(height), c.byref(border), c.byref(depth))
        x.XTranslateCoordinates(display, window, desktop, 0, 0, c.byref(px), c.byref(py), c.byref(owner))
        return px.value, py.value, width.value, height.value

    def move_pointer(px, py):
        xt.XTestFakeMotionEvent(display, -1, px, py, 0)
        x.XFlush(display)

    def button(down):
        xt.XTestFakeButtonEvent(display, 1, down, 0)
        x.XFlush(display)

    def click(px, py):
        move_pointer(px, py)
        button(True)
        button(False)
        time.sleep(0.5)

    environment = dict(os.environ, XDG_CONFIG_HOME=str(root/'config'), XDG_DATA_HOME=str(root/'data'), XDG_CACHE_HOME=str(root/'cache'))
    log = (root / 'window.log').open('w')
    app = subprocess.Popen([str(pathlib.Path(args.exe).resolve())], env=environment, stdout=log, stderr=log)
    try:
        window = None
        for attempt in range(100):
            if app.poll() is not None:
                raise RuntimeError('Launcher exited before showing a window')
            window = next((w for w in descendants(desktop) if prop(w, '_NET_WM_PID') == [app.pid] and prop(w, '_NET_WM_NAME') == 'Piwork MicroVM'), None)
            if window:
                break
            time.sleep(0.1)
        if window is None:
            raise RuntimeError('Owned window not found')
        time.sleep(2)
        hints = prop(window, 'WM_HINTS')
        modern = prop(window, '_NET_WM_ICON')
        legacy = bool(hints and hints[0] & 4 and hints[3])
        if not modern and not legacy:
            raise RuntimeError('Native window has no icon')
        if legacy:
            pixmap = hints[3]
            _, _, width, height = geometry(pixmap)
            image = x.XGetImage(display, pixmap, 0, 0, width, height, word(-1).value, 2)
            if not image:
                raise RuntimeError('Cannot read native icon pixmap')
            try:
                rgb = bytes(value for py in range(height) for px in range(width)
                            for pixel in [x.XGetPixel(image, px, py)]
                            for value in ((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255))
                Image.frombytes('RGB', (width, height), rgb).save(root/'evidence/linux-native-icon.png')
            finally:
                x.XDestroyImage(image)
        native = GdkX11.X11Window.foreign_new_for_display(Gdk.Display.get_default(), window)
        px, py, width, height = geometry(window)
        Gdk.pixbuf_get_from_window(native, 0, 0, width, height).savev(str(root/'evidence/linux-header.png'), 'png', [], [])
        click(px+width-33, py+30)
        app.wait(timeout=5)
        result = dict(executable=str(pathlib.Path(args.exe).resolve()), geometry=[width,height], display='WSLg Weston/XWayland',
                      modernIcon=bool(modern), legacyIcon=legacy, headerDrag=None, headerMinimize=None, headerIdleClose=app.returncode == 0, vmStarted=False)
        (root/'evidence/linux-window.json').write_text(json.dumps(result, indent=2)+'\n')
        if app.returncode:
            raise RuntimeError(f'Window controls failed: {result}')
        print(json.dumps(result))
    finally:
        if app.poll() is None:
            # This probe never clicks Start; termination is limited to its idle process.
            app.terminate()
            app.wait(timeout=5)
        log.close()
        x.XCloseDisplay(display)


if __name__ == '__main__':
    main()
