# -*- coding: utf-8 -*-

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



import struct

import time



import win32api

import win32con

import win32gui





class WinGuiAutoError(Exception):

    pass





def findSpecifiedTopWindow(wantedText=None, wantedClass=None):

    """

    Find a specific top-level window.



    :param wantedText: Window title text to search for

    :param wantedClass: Window class to search for

    :return: Window handle if found

    """

    return win32gui.FindWindow(wantedClass, wantedText)





def findPopupWindow(hwnd):

    """

    Find the popup window associated with the given window.



    :param hwnd: Parent window handle

    :return: Popup window handle

    """

    return win32gui.GetWindow(hwnd, win32con.GW_ENABLEDPOPUP)





def findTopWindow(wantedText=None, wantedClass=None, selectionFunction=None):

    """Find the hwnd of a top level window.

    You can identify windows using captions, classes, a custom selection

    function, or any combination of these. (Multiple selection criteria are

    ANDed. If this isn't what's wanted, use a selection function.)



    Parameters

    ----------

    wantedText

        Text which the required window's captions must contain.

    wantedClass

        Class to which the required window must belong.

    selectionFunction

        Window selection function. Reference to a function

        should be passed here. The function should take hwnd as

        an argument, and should return True when passed the

        hwnd of a desired window.



    Raises

    ------

    WinGuiAutoError

        When no window found.



    Usage example::



        optDialog = findTopWindow(wantedText="Options")

    """

    topWindows = findTopWindows(wantedText, wantedClass, selectionFunction)

    if topWindows:

        return topWindows[0]

    else:

        raise WinGuiAutoError(

            "No top level window found for wantedText="

            + repr(wantedText)

            + ", wantedClass="

            + repr(wantedClass)

            + ", selectionFunction="

            + repr(selectionFunction)

        )





def findTopWindows(wantedText=None, wantedClass=None, selectionFunction=None):

    """Find the hwnd of top level windows.



    You can identify windows using captions, classes, a custom selection

    function, or any combination of these. (Multiple selection criteria are

    ANDed. If this isn't what's wanted, use a selection function.)



    Parameters

    ----------

    wantedText

        Text which required windows' captions must contain.

    wantedClass

        Class to which required windows must belong.

    selectionFunction

        Window selection function. Reference to a function

        should be passed here. The function should take hwnd as

        an argument, and should return True when passed the

        hwnd of a desired window.



    Returns

    -------

    A list containing the window handles of all top level

    windows matching the supplied selection criteria.



    Usage example::



        optDialogs = findTopWindows(wantedText="Options")

    """

    results = []

    topWindows = []

    win32gui.EnumWindows(_windowEnumerationHandler, topWindows)

    for hwnd, windowText, windowClass in topWindows:

        if wantedText and _normaliseText(wantedText) not in _normaliseText(windowText):

            continue

        if wantedClass and not windowClass == wantedClass:

            continue

        if selectionFunction and not selectionFunction(hwnd):

            continue

        results.append(hwnd)

    return results





def dumpSpecifiedWindow(hwnd, wantedText=None, wantedClass=None):

    """

    Dump all child windows of a specified window.



    :param hwnd: Parent window handle

    :param wantedText: Text to filter child windows

    :param wantedClass: Class to filter child windows

    :return: List of child windows

    """

    windows = []

    hwndChild = None

    while True:

        hwndChild = win32gui.FindWindowEx(hwnd, hwndChild, wantedClass, wantedText)

        if hwndChild:

            textName = win32gui.GetWindowText(hwndChild)

            className = win32gui.GetClassName(hwndChild)

            windows.append((hwndChild, textName, className))

        else:

            return windows





def findSpecifiedWindows(top_hwnd, numChildWindows=70):

    """

    Find windows with a specific number of child windows.



    :param top_hwnd: Top level window handle

    :param numChildWindows: Number of child windows to match

    :return: Window content if match found

    """

    windows = []

    try:

        win32gui.EnumChildWindows(top_hwnd, _windowEnumerationHandler, windows)

    except win32gui.error:

        # No child windows

        return

    for window in windows:

        childHwnd, windowText, windowClass = window

        windowContent = dumpSpecifiedWindow(childHwnd)

        if len(windowContent) == numChildWindows:

            return windowContent

    return





def dumpWindow(hwnd):

    """Dump all controls from a window into a nested list



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



        replaceDialog = findTopWindow(wantedText='Replace')

        pprint.pprint(dumpWindow(replaceDialog))

    """

    windows = []

    try:

        win32gui.EnumChildWindows(hwnd, _windowEnumerationHandler, windows)

    except win32gui.error:

        # No child windows

        return

    windows = [list(window) for window in windows]

    for window in windows:

        childHwnd, windowText, windowClass = window

        window_content = dumpWindow(childHwnd)

        if window_content:

            window.append(window_content)

    return windows





def _closePopupWindow(top_hwnd, wantedText=None, wantedClass=None):

    """

    Close a popup window.



    :param top_hwnd: Top level window handle

    :param wantedText: Text of the control to click

    :param wantedClass: Class of the control to click

    :return: True if popup closed, False otherwise

    """

    hwnd_popup = findPopupWindow(top_hwnd)

    if hwnd_popup:

        hwnd_control = findControl(hwnd_popup, wantedText, wantedClass)

        clickButton(hwnd_control)

        return True

    return False





def closePopupWindows(top_hwnd):

    """

    Close all popup windows associated with the top window.



    :param top_hwnd: Top level window handle

    :return: None

    """

    while _closePopupWindow(top_hwnd):

        time.sleep(0.3)





def findControl(topHwnd, wantedText=None, wantedClass=None, selectionFunction=None):

    """Find a control.



    You can identify a control using caption, classe, a custom selection

    function, or any combination of these. (Multiple selection criteria are

    ANDed. If this isn't what's wanted, use a selection function.)



    Parameters

    ----------

    topHwnd

        The window handle of the top level window in which the

        required controls reside.

    wantedText

        Text which the required control's captions must contain.

    wantedClass

        Class to which the required control must belong.

    selectionFunction

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



        optDialog = findTopWindow(wantedText="Options")

        okButton = findControl(optDialog,

                               wantedClass="Button",

                               wantedText="OK")

    """

    controls = findControls(

        topHwnd,

        wantedText=wantedText,

        wantedClass=wantedClass,

        selectionFunction=selectionFunction,

    )

    if controls:

        return controls[0]

    else:

        raise WinGuiAutoError(

            "No control found for topHwnd="

            + repr(topHwnd)

            + ", wantedText="

            + repr(wantedText)

            + ", wantedClass="

            + repr(wantedClass)

            + ", selectionFunction="

            + repr(selectionFunction)

        )





def findControls(topHwnd, wantedText=None, wantedClass=None, selectionFunction=None):

    """Find controls.



    You can identify controls using captions, classes, a custom selection

    function, or any combination of these. (Multiple selection criteria are

    ANDed. If this isn't what's wanted, use a selection function.)



    Parameters

    ----------

    topHwnd

        The window handle of the top level window in which the

        required controls reside.

    wantedText

        Text which the required controls' captions must contain.

    wantedClass

        Class to which the required controls must belong.

    selectionFunction

        Control selection function. Reference to a function

        should be passed here. The function should take hwnd as

        an argument, and should return True when passed the

        hwnd of a desired control.



    Returns

    -------

    The window handles of the controls matching the

    supplied selection criteria.



    Usage example::



        optDialog = findTopWindow(wantedText="Options")

        def findButtons(hwnd, windowText, windowClass):

            return windowClass == "Button"

        buttons = findControl(optDialog, wantedText="Button")

    """



    def searchChildWindows(currentHwnd):

        results = []

        childWindows = []

        try:

            win32gui.EnumChildWindows(currentHwnd, _windowEnumerationHandler, childWindows)

        except win32gui.error:

            # This seems to mean that the control *cannot* have child windows,

            # i.e. not a container.

            return

        for childHwnd, windowText, windowClass in childWindows:

            descendentMatchingHwnds = searchChildWindows(childHwnd)

            if descendentMatchingHwnds:

                results += descendentMatchingHwnds



            if wantedText and _normaliseText(wantedText) not in _normaliseText(windowText):

                continue

            if wantedClass and not windowClass == wantedClass:

                continue

            if selectionFunction and not selectionFunction(childHwnd):

                continue

            results.append(childHwnd)

        return results



    return searchChildWindows(topHwnd)





def clickButton(hwnd):

    """Simulates a single mouse click on a button



    Parameters

    ----------

    hwnd

        Window handle of the required button.



    Usage example::



        okButton = findControl(fontDialog,

                               wantedClass="Button",

                               wantedText="OK")

        clickButton(okButton)

    """

    _sendNotifyMessage(hwnd, win32con.BN_CLICKED)





def click(hwnd):

    """

    Simulate a mouse click on a window.



    :param hwnd: Window handle to click

    :return: None

    """

    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, None, None)

    time.sleep(0.2)

    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, None)





def focusWindow(hwnd):

    """

    Bring window to focus and maximize it.



    :param hwnd: Window handle

    :return: None

    """

    win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)

    win32gui.SetForegroundWindow(hwnd)





def sendKey(hwnd, key_code):

    """

    Send a key press to a window.



    :param hwnd: Window handle

    :param key_code: Key code (e.g., win32con.VK_F1)

    :return: None

    """

    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, key_code, 0)

    time.sleep(0.2)

    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, key_code, 0)





def clickStatic(hwnd):

    """Simulates a single mouse click on a static control



    Parameters

    ----------

    hwnd

        Window handle of the required static control.

    """

    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, None, None)

    time.sleep(0.2)

    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, None, None)





def doubleClickStatic(hwnd):

    """Simulates a double mouse click on a static control



    Parameters

    ----------

    hwnd

        Window handle of the required static control.

    """

    clickStatic(hwnd)

    time.sleep(0.2)

    clickStatic(hwnd)





def getComboboxItems(hwnd):

    """Get all items from a combobox



    Parameters

    ----------

    hwnd

        Window handle of the required combobox.



    Returns

    -------

    List of strings containing all items in the combobox.

    """

    return _getMultipleWindowValues(hwnd, _getComboboxItem)





def selectComboboxItem(hwnd, item):

    """Selects an item from a combobox



    Parameters

    ----------

    hwnd

        Window handle of the required combobox.

    item

        The item to select. Can be an index (integer) or text (string).

    """

    if isinstance(item, str):

        item = _getComboboxItemIndex(hwnd, item)

    _sendNotifyMessage(hwnd, win32con.CBN_SELCHANGE, item)





def getListboxItems(hwnd):

    """Get all items from a listbox



    Parameters

    ----------

    hwnd

        Window handle of the required listbox.



    Returns

    -------

    List of strings containing all items in the listbox.

    """

    return _getMultipleWindowValues(hwnd, _getListboxItem)





def selectListboxItem(hwnd, item):

    """Selects an item from a listbox



    Parameters

    ----------

    hwnd

        Window handle of the required listbox.

    item

        The item to select. Can be an index (integer) or text (string).

    """

    if isinstance(item, str):

        item = _getListboxItemIndex(hwnd, item)

    _sendNotifyMessage(hwnd, win32con.LBN_SELCHANGE, item)





def setText(hwnd, text):

    """Set the text of an edit control



    Parameters

    ----------

    hwnd

        Window handle of the required edit control.

    text

        The text to enter.

    """

    win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, None, text)





def getText(hwnd):

    """Get the text of a control



    Parameters

    ----------

    hwnd

        Window handle of the required control.



    Returns

    -------

    String containing the text of the control.

    """

    return win32gui.GetWindowText(hwnd)





def _windowEnumerationHandler(hwnd, resultList):

    """Callback for window enumeration"""

    resultList.append((hwnd, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd)))





def _normaliseText(text):

    """Normalise text for comparison"""

    return text.lower()





def _sendNotifyMessage(hwnd, message, wParam=None, lParam=None):

    """Send a notify message to a window"""

    win32gui.SendMessage(

        win32api.GetParent(hwnd),

        win32con.WM_COMMAND,

        win32api.MAKELONG(win32api.GetWindowLong(hwnd, win32con.GWL_ID), message),

        hwnd,

    )





def _getComboboxItem(hwnd, index):

    """Get a combobox item"""

    return win32gui.SendMessage(hwnd, win32con.CB_GETLBTEXT, index, None)





def _getComboboxItemIndex(hwnd, text):

    """Get the index of a combobox item by text"""

    return win32gui.SendMessage(hwnd, win32con.CB_FINDSTRINGEXACT, -1, text)





def _getListboxItem(hwnd, index):

    """Get a listbox item"""

    return win32gui.SendMessage(hwnd, win32con.LB_GETTEXT, index, None)





def _getListboxItemIndex(hwnd, text):

    """Get the index of a listbox item by text"""

    return win32gui.SendMessage(hwnd, win32con.LB_FINDSTRINGEXACT, -1, text)





def _getMultipleWindowValues(hwnd, getItemFunction):

    """Get multiple values from a window control"""

    result = []

    index = 0

    while True:

        item = getItemFunction(hwnd, index)

        if item:

            result.append(item)

            index += 1

        else:

            break

    return result

