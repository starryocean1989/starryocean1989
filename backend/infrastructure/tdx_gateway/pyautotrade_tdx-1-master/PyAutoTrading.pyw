# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
"""
PyAutoTrading - 自动化股票交易系统.

该模块提供基于通达信交易软件的自动化股票交易功能，包括实时监控、
自动下单、历史记录等功能。

QQ群： 486224275
作者： 人在江湖
"""
__author__ = "人在江湖"

import configparser
import datetime
import pickle
import threading
import time
import tkinter.messagebox
from tkinter import (
    Button,
    CENTER,
    DISABLED,
    Entry,
    Frame,
    LEFT,
    Label,
    NORMAL,
    RIGHT,
    Scrollbar,
    StringVar,
    Tk,
    Toplevel,
    Y,
)
from tkinter.ttk import Combobox, Spinbox, Treeview
from typing import List, Tuple

import pandas as pd

import tushare as ts

from winguiauto import (
    click,
    close_popup_windows,
    find_specified_top_window,
    find_specified_windows,
    get_text,
    set_text,
)

IS_START = False
IS_MONITOR = True
set_stock_info = []
order_msg = []
actual_stock_info = []
is_ordered = [1] * 5  # 1：未下单  0：已下单


def get_config_data():
    """
    读取配置文件参数.

    :return: 双向委托界面下，控件的数量
    """
    cp = configparser.ConfigParser()
    cp.read("pyautotrading.ini")
    num_child_windows = cp.getint("tradeVersion", "numChildWindows")
    return num_child_windows


# def pickHwndOfControls(top_hwnd, num_child_windows):
#     cleaned_hwnd_controls = []
#     hwnd_controls = findSpecifiedWindows(top_hwnd, num_child_windows)
#     for Hwnd, text_name, class_name in hwnd_controls:
#         if class_name in ('Button', 'Edit'):
#             cleaned_hwnd_controls.append((Hwnd, text_name, class_name))
#     return cleaned_hwnd_controls


def get_running_money(sub_hwnds):
    """
    获取可用资金.

    :param sub_hwnds: 双向委托操作界面下的控件句柄列表
    :return: 可用资金
    """
    return get_text(sub_hwnds[12][1])


def buy(sub_hwnds, code, stop_price, quantity):
    """
    买函数，自动填写3个Edit控件，及点击买入按钮.

    :param sub_hwnds: 双向委托操作界面下的控件句柄列表
    :param code: 股票代码，字符串
    :param stop_price: 涨停市价， 字符串
    :param quantity: 买入股票 数量，字符串
    :return: None
    """
    set_text(sub_hwnds[0][0], code)
    set_text(sub_hwnds[1][0], stop_price)
    set_text(sub_hwnds[3][0], quantity)
    time.sleep(0.3)
    click(sub_hwnds[5][0])
    time.sleep(0.3)


def sell(sub_hwnds, code, stop_price, quantity):
    """
    卖函数，自动填写3个Edit控件，及点击卖出按钮.

    :param sub_hwnds: 双向委托操作界面下的控件句柄列表
    :param code: 股票代码，字符串
    :param stop_price: 涨停市价， 字符串
    :param quantity: 卖出股票 数量，字符串
    :return: None
    """
    set_text(sub_hwnds[24][0], code)
    set_text(sub_hwnds[25][0], stop_price)
    set_text(sub_hwnds[27][0], quantity)
    time.sleep(0.3)
    click(sub_hwnds[29][0])
    time.sleep(0.3)


def order(sub_hwnds, code, stop_prices, quantity, direction):
    """
    买卖函数.

    :param sub_hwnds: 双向委托操作界面下的控件句柄列表
    :param code: 股票代码， 字符串
    :param stop_prices: 涨跌停价格，字符串
    :param quantity: 买卖数量，字符串
    :param direction: 交易方向，字符串
    :return: None
    """
    if direction == "B":
        buy(sub_hwnds, code, stop_prices[0], quantity)
    if direction == "S":
        sell(sub_hwnds, code, stop_prices[1], quantity)


def trading_init():
    """
    获得交易软件句柄.

    :return: 顶层窗口句柄，双向委托操作界面下的控件句柄列表
    """
    top_hwnd = find_specified_top_window(wanted_class="TdxW_MainFrame_Class")
    if top_hwnd == 0:
        tkinter.messagebox.showerror("错误", "请先打开交易软件，再运行本软件")
        return top_hwnd, []
    else:
        sub_hwnds = find_specified_windows(top_hwnd, get_config_data())
    return top_hwnd, sub_hwnds


def pick_code_from_items(items_info):
    """
    提取股票代码.

    :param items_info: UI下各项输入信息
    :return: 股票代码列表
    """
    stock_codes = []
    for item in items_info:
        stock_codes.append(item[0])
    return stock_codes


def get_stock_data(items_info: List) -> List[Tuple[str, str, str, Tuple[str, str]]]:
    """
    获取股票实时数据.

    :param items_info: UI下各项输入信息
    :return: 股票实时数据
    """
    # pylint: disable=unsubscriptable-object
    code_name_price = []
    stock_codes = pick_code_from_items(items_info)
    try:
        df_result = ts.get_realtime_quotes(stock_codes)
        if not isinstance(df_result, pd.DataFrame):
            raise ValueError("Expected DataFrame from tushare")
        df = df_result
        df_len = len(df)
        for stock_code in stock_codes:
            is_found = False
            for i in range(df_len):
                actual_code = df["code"][i]
                if stock_code == actual_code:
                    actual_name = df["name"][i]
                    pre_close = float(str(df["pre_close"].iloc[i]))
                    if "ST" in actual_name:
                        highest = str(round(pre_close * 1.05, 2))
                        lowest = str(round(pre_close * 0.95, 2))
                        code_name_price.append(
                            (
                                actual_code,
                                actual_name,
                                df["price"][i],
                                (highest, lowest),
                            )
                        )
                    else:
                        highest = str(round(pre_close * 1.1, 2))
                        lowest = str(round(pre_close * 0.95, 2))
                        code_name_price.append(
                            (
                                actual_code,
                                actual_name,
                                df["price"][i],
                                (highest, lowest),
                            )
                        )
                    is_found = True
                    break
            if is_found is False:
                code_name_price.append(("", "", "", ("", "")))
    except (ConnectionError, ValueError, KeyError, AttributeError):
        # 网络不行，返回空
        code_name_price = [("", "", "", ("", ""))] * 5
    return code_name_price


def monitor():
    """
    实时监控函数.

    :return: None
    """
    # pylint: disable=global-statement,global-variable-not-assigned
    global actual_stock_info, order_msg, is_ordered
    count = 0
    top_hwnd, sub_hwnds = trading_init()
    # 如果top_hwnd为零，直接终止循环
    while IS_MONITOR and top_hwnd:
        if count % 100 == 0:
            # clickButton(sub_hwnd[12][0])  # 点击刷新按钮
            time.sleep(1)
        time.sleep(3)
        count += 1
        if IS_START:
            actual_stock_info = get_stock_data(set_stock_info)
            # print('actual_stock_info', actual_stock_info)
            for row, (actual_code, actual_name, actual_price, stop_prices) in enumerate(
                actual_stock_info
            ):
                if (
                    IS_START
                    and actual_code
                    and is_ordered[row] == 1
                    and set_stock_info[row][1]
                    and set_stock_info[row][2] > 0
                    and set_stock_info[row][3]
                    and set_stock_info[row][4]
                    and datetime.datetime.now().time() > set_stock_info[row][5]
                ):
                    if (
                        IS_START
                        and set_stock_info[row][1] == ">"
                        and float(actual_price) > set_stock_info[row][2]
                    ):
                        dt = datetime.datetime.now()
                        order(
                            sub_hwnds,
                            actual_code,
                            stop_prices,
                            set_stock_info[row][4],
                            set_stock_info[row][3],
                        )
                        close_popup_windows(top_hwnd)
                        order_msg.append(
                            (
                                dt.strftime("%x"),
                                dt.strftime("%X"),
                                actual_code,
                                actual_name,
                                set_stock_info[row][3],
                                actual_price,
                                set_stock_info[row][4],
                                "已下单",
                            )
                        )
                        is_ordered[row] = 0

                    if (
                        IS_START
                        and set_stock_info[row][1] == "<"
                        and float(actual_price) < set_stock_info[row][2]
                    ):
                        dt = datetime.datetime.now()
                        order(
                            sub_hwnds,
                            actual_code,
                            stop_prices,
                            set_stock_info[row][4],
                            set_stock_info[row][3],
                        )
                        close_popup_windows(top_hwnd)
                        order_msg.append(
                            (
                                dt.strftime("%x"),
                                dt.strftime("%X"),
                                actual_code,
                                actual_name,
                                set_stock_info[row][3],
                                actual_price,
                                set_stock_info[row][4],
                                "已下单",
                            )
                        )
                        is_ordered[row] = 0


class StockGui:
    """股票交易GUI界面类."""

    def __init__(self):
        """初始化GUI界面."""
        self.window = Tk()
        self.window.title("自动化股票交易")
        self.window.resizable(False, False)

        frame1 = Frame(self.window)
        frame1.pack(padx=10, pady=10)

        Label(frame1, text="股票代码", width=8, justify=CENTER).grid(
            row=1, column=1, padx=5, pady=5
        )
        Label(frame1, text="股票名称", width=8, justify=CENTER).grid(
            row=1, column=2, padx=5, pady=5
        )
        Label(frame1, text="当前价格", width=8, justify=CENTER).grid(
            row=1, column=3, padx=5, pady=5
        )
        Label(frame1, text="关系", width=4, justify=CENTER).grid(
            row=1, column=4, padx=5, pady=5
        )
        Label(frame1, text="价格", width=8, justify=CENTER).grid(
            row=1, column=5, padx=5, pady=5
        )
        Label(frame1, text="方向", width=4, justify=CENTER).grid(
            row=1, column=6, padx=5, pady=5
        )
        Label(frame1, text="数量", width=8, justify=CENTER).grid(
            row=1, column=7, padx=5, pady=5
        )
        Label(frame1, text="时间可选", width=8, justify=CENTER).grid(
            row=1, column=8, padx=5, pady=5
        )
        Label(frame1, text="状态", width=4, justify=CENTER).grid(
            row=1, column=9, padx=5, pady=5
        )

        self.rows = 5
        self.cols = 9

        self.variable = []
        for row in range(self.rows):
            self.variable.append([])
            for _col in range(self.cols):
                temp = StringVar()
                self.variable[row].append(temp)

        for row in range(self.rows):
            Entry(frame1, textvariable=self.variable[row][0], width=8).grid(
                row=row + 2, column=1, padx=5, pady=5
            )
            Entry(
                frame1, textvariable=self.variable[row][1], state=DISABLED, width=8
            ).grid(row=row + 2, column=2, padx=5, pady=5)
            Entry(
                frame1, textvariable=self.variable[row][2], state=DISABLED, width=8
            ).grid(row=row + 2, column=3, padx=5, pady=5)
            Combobox(
                frame1, values=("<", ">"), textvariable=self.variable[row][3], width=2
            ).grid(row=row + 2, column=4, padx=5, pady=5)
            Spinbox(
                frame1,
                from_=0,
                to=1000,
                textvariable=self.variable[row][4],
                increment=0.01,
                width=6,
            ).grid(row=row + 2, column=5, padx=5, pady=5)
            Combobox(
                frame1, values=("B", "S"), textvariable=self.variable[row][5], width=2
            ).grid(row=row + 2, column=6, padx=5, pady=5)
            Spinbox(
                frame1,
                from_=0,
                to=100000,
                textvariable=self.variable[row][6],
                increment=100,
                width=6,
            ).grid(row=row + 2, column=7, padx=5, pady=5)
            Entry(frame1, textvariable=self.variable[row][7], width=8).grid(
                row=row + 2, column=8, padx=5, pady=5
            )
            Entry(
                frame1, textvariable=self.variable[row][8], state=DISABLED, width=5
            ).grid(row=row + 2, column=9, padx=5, pady=5)

        frame3 = Frame(self.window)
        frame3.pack(padx=10, pady=10)
        self.start_bt = Button(frame3, text="开始", command=self.start)
        self.start_bt.pack(side=LEFT)
        self.set_bt = Button(frame3, text="重置买卖", command=self.set_flags)
        self.set_bt.pack(side=LEFT)
        Button(frame3, text="历史记录", command=self.display_his_records).pack(
            side=LEFT
        )
        Button(frame3, text="保存", command=self.save).pack(side=LEFT)
        self.load_bt = Button(frame3, text="载入", command=self.load)
        self.load_bt.pack(side=LEFT)

        self.window.protocol(name="WM_DELETE_WINDOW", func=self.close)
        self.window.after(100, self.update_controls)
        self.window.mainloop()

    def display_his_records(self):
        """
        显示历史信息.

        :return: None
        """
        tp = Toplevel()
        tp.title("历史记录")
        tp.resizable(False, True)
        scrollbar = Scrollbar(tp)
        scrollbar.pack(side=RIGHT, fill=Y)
        col_name = [
            "日期",
            "时间",
            "证券代码",
            "证券名称",
            "方向",
            "价格",
            "数量",
            "备注",
        ]
        tree = Treeview(
            tp,
            show="headings",
            columns=col_name,
            height=30,
            yscrollcommand=scrollbar.set,
        )
        tree.pack(expand=1, fill=Y)
        scrollbar.config(command=tree.yview)
        for name in col_name:
            tree.heading(name, text=name)
            tree.column(name, width=70, anchor=CENTER)

        for msg in order_msg:
            tree.insert("", 0, values=msg)

    def save(self):
        """
        保存设置.

        :return: None
        """
        # pylint: disable=global-statement,global-variable-not-assigned
        global set_stock_info  # assigned in get_items() method
        self.get_items()
        with open("stockInfo.dat", "wb") as fp:
            pickle.dump(set_stock_info, fp)
            # pickle.dump(actual_stock_info, fp)
            pickle.dump(order_msg, fp)

    def load(self):
        """
        载入设置.

        :return: None
        """
        global set_stock_info, order_msg  # pylint: disable=global-statement
        with open("stockInfo.dat", "rb") as fp:
            set_stock_info = pickle.load(fp)
            # actual_stock_info = pickle.load(fp)
            order_msg = pickle.load(fp)
        for row in range(self.rows):
            for col in range(self.cols):
                if col == 0:
                    self.variable[row][col].set(set_stock_info[row][0])
                elif col == 3:
                    self.variable[row][col].set(set_stock_info[row][1])
                elif col == 4:
                    self.variable[row][col].set(set_stock_info[row][2])
                elif col == 5:
                    self.variable[row][col].set(set_stock_info[row][3])
                elif col == 6:
                    self.variable[row][col].set(set_stock_info[row][4])
                elif col == 7:
                    temp = set_stock_info[row][5].strftime("%X")
                    if temp == "01:00:00":
                        self.variable[row][col].set("")
                    else:
                        self.variable[row][col].set(temp)

    def set_flags(self):
        """
        重置买卖标志.

        :return: None
        """
        global is_ordered  # pylint: disable=global-statement
        if IS_START is False:
            is_ordered = [1] * 5

    def update_controls(self):
        """
        实时股票名称、价格、状态信息.

        :return: None
        """
        if IS_START:
            print("actual_stock_info", actual_stock_info)
            for row, (actual_code, actual_name, actual_price, _) in enumerate(
                actual_stock_info
            ):
                self.variable[row][1].set(actual_name)
                self.variable[row][2].set(str(actual_price))
                if actual_code:
                    if is_ordered[row] == 1:
                        self.variable[row][8].set("监控中")
                    elif is_ordered[row] == 0:
                        self.variable[row][8].set("已下单")
                else:
                    self.variable[row][8].set("")

        self.window.after(3000, self.update_controls)

    def start(self):
        """
        启动停止.

        :return: None
        """
        global IS_START  # pylint: disable=global-statement
        if IS_START is False:
            IS_START = True
        else:
            IS_START = False

        if IS_START:
            self.get_items()
            # print(set_stock_info)
            self.start_bt["text"] = "停止"
            self.set_bt["state"] = DISABLED
            self.load_bt["state"] = DISABLED
        else:
            self.start_bt["text"] = "开始"
            self.set_bt["state"] = NORMAL
            self.load_bt["state"] = NORMAL

    def close(self):
        """
        关闭程序时，停止monitor线程.

        :return: None
        """
        global IS_MONITOR  # pylint: disable=global-statement
        IS_MONITOR = False
        self.window.quit()

    def get_items(self):
        """
        获取UI上用户输入的各项数据.

        :return: None
        """
        global set_stock_info  # pylint: disable=global-statement
        set_stock_info = []

        # 获取买卖价格数量输入项等
        for row in range(self.rows):
            set_stock_info.append([])
            for col in range(self.cols):
                temp = self.variable[row][col].get().strip()
                if col == 0:
                    if len(temp) == 6 and temp.isdigit():  # 判断股票代码是否为6位数
                        set_stock_info[row].append(temp)
                    else:
                        set_stock_info[row].append("")
                elif col == 3:
                    if temp in (">", "<"):
                        set_stock_info[row].append(temp)
                    else:
                        set_stock_info[row].append("")
                elif col == 4:
                    try:
                        price = float(temp)
                        if price > 0:
                            # 把价格转为数字
                            set_stock_info[row].append(price)
                        else:
                            set_stock_info[row].append(0)
                    except ValueError:
                        set_stock_info[row].append(0)
                elif col == 5:
                    if temp in ("B", "S"):
                        set_stock_info[row].append(temp)
                    else:
                        set_stock_info[row].append("")
                elif col == 6:
                    if temp.isdigit() and int(temp) >= 100:
                        set_stock_info[row].append(str(int(temp) // 100 * 100))
                    else:
                        set_stock_info[row].append("")
                elif col == 7:
                    try:
                        set_stock_info[row].append(
                            datetime.datetime.strptime(temp, "%H:%M:%S").time()
                        )
                    except ValueError:
                        set_stock_info[row].append(
                            datetime.datetime.strptime("1:00:00", "%H:%M:%S").time()
                        )


if __name__ == "__main__":
    t1 = threading.Thread(target=StockGui)
    t2 = threading.Thread(target=monitor)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
