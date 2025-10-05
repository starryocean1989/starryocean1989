# -*- coding: utf-8 -*-
# pylint: disable=c-extension-no-member

# Module     : winGuiAuto.py

# Synopsis   : Windows GUI automation utilities

# Programmer : Simon Brunning - simon@brunningonline.net

# Date       : 25 June 2003

# Version    : 1.0 pre-alpha 2

# Copyright  : Released to the public domain. Provided as-is, with no warranty.

# Notes      : Requires Python 2.3, win32all and ctypes

"""Windows GUI automation utilities.

Until I get around to writing some docs and examples, the tests at the foot of
this module should serve to get you started.
"""

import time

import win32api

import win32con

import win32gui


class WinGuiAutoError(Exception):
    """Exception raised for WinGuiAuto errors."""


def find_specified_top_window(wanted_text=None, wanted_class=None):
    """Find a specific top-level window.

    :param wanted_text: Window title text to search for
    :param wanted_class: Window class to search for
    :return: Window handle if found
    """
    return win32gui.FindWindow(wanted_class, wanted_text)


def find_popup_window(hwnd):
    """Find the popup window associated with the given window.

    :param hwnd: Parent window handle
    :return: Popup window handle
    """
    return win32gui.GetWindow(hwnd, win32con.GW_ENABLEDPOPUP)


def find_top_window(wanted_text=None, wanted_class=None,
                    selection_function=None):
    """Find the hwnd of a top level window.

    You can identify windows using captions, classes, a custom selection
    function, or any combination of these. (Multiple selection criteria are
    ANDed. If this isn't what's wanted, use a selection function.)

    Parameters
    ----------
    wanted_text
        Text which the required window's captions must contain.
    wanted_class
        Class to which the required window must belong.
    selection_function
        Window selection function. Reference to a function
        should be passed here. The function should take hwnd as
        an argument, and should return True when passed the
        hwnd of a desired window.

    Raises
    ------
    WinGuiAutoError
        When no window found.

    Usage example::

        optDialog = findTopWindow(wanted_text="Options")
    """
    top_windows = find_top_windows(wanted_text, wanted_class,
                                   selection_function)
    if top_windows:
        return top_windows[0]
    else:
        raise WinGuiAutoError(
            "No top level window found for wanted_text="
            + repr(wanted_text)
            + ", wanted_class="
            + repr(wanted_class)
            + ", selection_function="
            + repr(selection_function)
        )


def find_top_windows(wanted_text=None, wanted_class=None,
                     selection_function=None):
    """Find the hwnd of top level windows.

    You can identify windows using captions, classes, a custom selection
    function, or any combination of these. (Multiple selection criteria are
    ANDed. If this isn't what's wanted, use a selection function.)

    Parameters
    ----------
    wanted_text
        Text which required windows' captions must contain.
    wanted_class
        Class to which required windows must belong.
    selection_function
        Window selection function. Reference to a function
        should be passed here. The function should take hwnd as
        an argument, and should return True when passed the
        hwnd of a desired window.

    Returns
    -------
    A list containing the window handles of all top level
    windows matching the supplied selection criteria.

    Usage example::

        optDialogs = findTopWindows(wanted_text="Options")
    """
    results = []
    top_windows = []
    win32gui.EnumWindows(_window_enumeration_handler, top_windows)
    for hwnd, window_text, window_class in top_windows:
        if (wanted_text and _normalise_text(wanted_text) not in
                _normalise_text(window_text)):
            continue
        if wanted_class and window_class != wanted_class:
            continue
        if selection_function and not selection_function(hwnd):
            continue
        results.append(hwnd)
    return results


def dump_specified_window(hwnd, wanted_text=None, wanted_class=None):
    """Dump all child windows of a specified window.

    :param hwnd: Parent window handle
    :param wanted_text: Text to filter child windows
    :param wanted_class: Class to filter child windows
    :return: List of child windows
    """
    windows = []
    hwnd_child = None
    while True:
        hwnd_child = win32gui.FindWindowEx(
            hwnd, hwnd_child, wanted_class, wanted_text
        )
        if hwnd_child:
            text_name = win32gui.GetWindowText(hwnd_child)
            class_name = win32gui.GetClassName(hwnd_child)
            windows.append((hwnd_child, text_name, class_name))
        else:
            return windows


def find_specified_windows(top_hwnd, num_child_windows=70):
    """Find windows with a specific number of child windows.

    :param top_hwnd: Top level window handle
    :param num_child_windows: Number of child windows to match
    :return: Window content if match found
    """
    windows = []
    try:
        win32gui.Enum_child_windows(
            top_hwnd, _window_enumeration_handler, windows
        )
    except win32gui.error:
        # No child windows
        return
    for window in windows:
        child_hwnd, _window_text, _window_class = window
        window_content = dump_specified_window(child_hwnd)
        if len(window_content) == num_child_windows:
            return window_content
    return


def dump_window(hwnd):
    """Dump all controls from a window into a nested list.

    Useful during development, allowing to you discover the structure of the
    contents of a window, showing the text and class of all contained controls.

    Parameters
    ----------
    hwnd
        The window handle of the top level window to dump.

    Returns
    -------
    A nested list of controls. Each entry consists of the
    control's hwnd, its text, its class, and its sub-controls, if any.

    Usage example::

        replaceDialog = findTopWindow(wanted_text='Replace')
        pprint.pprint(dump_window(replaceDialog))
    """
    windows = []
    try:
        win32gui.Enum_child_windows(hwnd, _window_enumeration_handler, windows)
    except win32gui.error:
        # No child windows
        return
    windows = [list(window) for window in windows]
    for window in windows:
        child_hwnd, _window_text, _window_class = window
        window_content = dump_window(child_hwnd)
        if window_content:
            window.append(window_content)
    return windows


def _close_popup_window(top_hwnd, wanted_text=None, wanted_class=None):
    """Close a popup window.

    :param top_hwnd: Top level window handle
    :param wanted_text: Text of the control to click
    :param wanted_class: Class of the control to click
    :return: True if popup closed, False otherwise
    """
    hwnd_popup = find_popup_window(top_hwnd)
    if hwnd_popup:
        hwnd_control = find_control(hwnd_popup, wanted_text, wanted_class)
        click_button(hwnd_control)
        return True
    return False


def close_popup_windows(top_hwnd):
    """Close all popup windows associated with the top window.

    :param top_hwnd: Top level window handle
    :return: None
    """
    while _close_popup_window(top_hwnd):
        time.sleep(0.3)


def find_control(top_hwnd, wanted_text=None, wanted_class=None,
                 selection_function=None):
    """Find a control.

    You can identify a control using caption, classe, a custom selection
    function, or any combination of these. (Multiple selection criteria are
    ANDed. If this isn't what's wanted, use a selection function.)

    Parameters
    ----------
    top_hwnd
        The window handle of the top level window in which the
        required controls reside.
    wanted_text
        Text which the required control's captions must contain.
    wanted_class
        Class to which the required control must belong.
    selection_function
        Control selection function. Reference to a function
        should be passed here. The function should take hwnd as
        an argument, and should return True when passed the
        hwnd of the desired control.

    Returns
    -------
    The window handle of the first control matching the
    supplied selection criteria.

    Raises
    ------
    WinGuiAutoError, when no control found.

    Usage example::

        optDialog = findTopWindow(wanted_text="Options")
        okButton = findControl(optDialog,
                               wanted_class="Button",
                               wanted_text="OK")
    """
    controls = find_controls(
        top_hwnd,
        wanted_text=wanted_text,
        wanted_class=wanted_class,
        selection_function=selection_function,
    )
    if controls:
        return controls[0]
    else:
        raise WinGuiAutoError(
            "No control found for top_hwnd="
            + repr(top_hwnd)
            + ", wanted_text="
            + repr(wanted_text)
            + ", wanted_class="
            + repr(wanted_class)
            + ", selection_function="
            + repr(selection_function)
        )


def find_controls(top_hwnd, wanted_text=None, wanted_class=None,
                  selection_function=None):
    """Find controls.

    You can identify controls using captions, classes, a custom selection
    function, or any combination of these. (Multiple selection criteria are
    ANDed. If this isn't what's wanted, use a selection function.)

    Parameters
    ----------
    top_hwnd
        The window handle of the top level window in which the
        required controls reside.
    wanted_text
        Text which the required controls' captions must contain.
    wanted_class
        Class to which the required controls must belong.
    selection_function
        Control selection function. Reference to a function
        should be passed here. The function should take hwnd as
        an argument, and should return True when passed the
        hwnd of a desired control.

    Returns
    -------
    The window handles of the controls matching the
    supplied selection criteria.

    Usage example::

        optDialog = findTopWindow(wanted_text="Options")
        def findButtons(hwnd, window_text, window_class):
            return window_class == "Button"
        buttons = findControl(optDialog, wanted_text="Button")
    """

    def search_child_windows(current_hwnd):
        results = []
        child_windows = []
        try:
            win32gui.Enum_child_windows(
                current_hwnd, _window_enumeration_handler, child_windows
            )
        except win32gui.error:
            # This seems to mean that the control *cannot* have child windows,
            # i.e. not a container.
            return

        for child_hwnd, window_text, window_class in child_windows:
            descendent_matching_hwnds = search_child_windows(child_hwnd)
            if descendent_matching_hwnds:
                results += descendent_matching_hwnds

            if (wanted_text and _normalise_text(wanted_text) not in
                    _normalise_text(window_text)):
                continue
            if wanted_class and window_class != wanted_class:
                continue
            if selection_function and not selection_function(child_hwnd):
                continue
            results.append(child_hwnd)
        return results

    return search_child_windows(top_hwnd)


def click_button(hwnd):
    """Click a button with a single mouse click.

    Parameters
    ----------
    hwnd
        Window handle of the required button.

    Usage example::

        okButton = findControl(fontDialog,
                               wanted_class="Button",
                               wanted_text="OK")
        clickButton(okButton)
    """
    _send_notify_message(hwnd, win32con.BN_CLICKED)


def click(hwnd):
    """Simulate a mouse click on a window.

    :param hwnd: Window handle to click
    :return: None
    """
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, None, None)
    time.sleep(0.2)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, None)


def focus_window(hwnd):
    """Bring window to focus and maximize it.

    :param hwnd: Window handle
    :return: None
    """
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
    win32gui.SetForegroundWindow(hwnd)


def send_key(hwnd, key_code):
    """Send a key press to a window.

    :param hwnd: Window handle
    :param key_code: Key code (e.g., win32con.VK_F1)
    :return: None
    """
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, key_code, 0)
    time.sleep(0.2)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, key_code, 0)


def click_static(hwnd):
    """Simulate a single mouse click on a static control.

    Parameters
    ----------
    hwnd
        Window handle of the required static control.
    """
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, None, None)
    time.sleep(0.2)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, None)


def double_click_static(hwnd):
    """Simulate a double mouse click on a static control.

    Parameters
    ----------
    hwnd
        Window handle of the required static control.
    """
    click_static(hwnd)
    time.sleep(0.2)
    click_static(hwnd)


def get_combobox_items(hwnd):
    """Get all items from a combobox.

    Parameters
    ----------
    hwnd
        Window handle of the required combobox.

    Returns
    -------
    List of strings containing all items in the combobox.
    """
    return _get_multiple_window_values(hwnd, _get_combobox_item)


def select_combobox_item(hwnd, item):
    """Select an item from a combobox.

    Parameters
    ----------
    hwnd
        Window handle of the required combobox.
    item
        The item to select. Can be an index (integer) or text (string).
    """
    if isinstance(item, str):
        item = _get_combobox_item_index(hwnd, item)
    _send_notify_message(hwnd, win32con.CBN_SELCHANGE, item)


def get_listbox_items(hwnd):
    """Get all items from a listbox.

    Parameters
    ----------
    hwnd
        Window handle of the required listbox.

    Returns
    -------
    List of strings containing all items in the listbox.
    """
    return _get_multiple_window_values(hwnd, _get_listbox_item)


def select_listbox_item(hwnd, item):
    """Select an item from a listbox.

    Parameters
    ----------
    hwnd
        Window handle of the required listbox.
    item
        The item to select. Can be an index (integer) or text (string).
    """
    if isinstance(item, str):
        item = _get_listbox_item_index(hwnd, item)
    _send_notify_message(hwnd, win32con.LBN_SELCHANGE, item)


def set_text(hwnd, text):
    """Set the text of an edit control.

    Parameters
    ----------
    hwnd
        Window handle of the required edit control.
    text
        The text to enter.
    """
    win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, None, text)


def get_text(hwnd):
    """Get the text of a control.

    Parameters
    ----------
    hwnd
        Window handle of the required control.

    Returns
    -------
    String containing the text of the control.
    """
    return win32gui.GetWindowText(hwnd)


def _window_enumeration_handler(hwnd, result_list):
    """Handle window enumeration callback."""
    result_list.append(
        (hwnd, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd))
    )


def _normalise_text(text):
    """Normalise text for comparison."""
    return text.lower()


def _send_notify_message(hwnd, message, item=None):
    """Send a notify message to a window."""
    # For selection change messages, include the item in the wParam
    if (message in (win32con.CBN_SELCHANGE, win32con.LBN_SELCHANGE) and
            item is not None):
        wparam = win32api.MAKELONG(
            win32api.GetWindowLong(hwnd, win32con.GWL_ID), item
        )
    else:
        wparam = win32api.MAKELONG(
            win32api.GetWindowLong(hwnd, win32con.GWL_ID), message
        )

    win32gui.SendMessage(
        win32api.GetParent(hwnd),
        win32con.WM_COMMAND,
        wparam,
        hwnd,
    )


def _get_combobox_item(hwnd, index):
    """Get a combobox item."""
    return win32gui.SendMessage(hwnd, win32con.CB_GETLBTEXT, index, None)


def _get_combobox_item_index(hwnd, text):
    """Get the index of a combobox item by text."""
    return win32gui.SendMessage(hwnd, win32con.CB_FINDSTRINGEXACT, -1, text)


def _get_listbox_item(hwnd, index):
    """Get a listbox item."""
    return win32gui.SendMessage(hwnd, win32con.LB_GETTEXT, index, None)


def _get_listbox_item_index(hwnd, text):
    """Get the index of a listbox item by text."""
    return win32gui.SendMessage(hwnd, win32con.LB_FINDSTRINGEXACT, -1, text)


def _get_multiple_window_values(hwnd, get_item_function):
    """Get multiple values from a window control."""
    result = []
    index = 0
    while True:
        item = get_item_function(hwnd, index)
        if item:
            result.append(item)
            index += 1
        else:
            break
    return result
