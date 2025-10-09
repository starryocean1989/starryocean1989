// TradeXDemo.cpp : 定义控制台应用程序的入口点。
//

#include "stdafx.h"

#include <iostream>

using namespace std;

#include "TradeX.h"

int test_hq_funcs(const char *pszHqSvrIP, short nPort);

char g_szResult[1024 *1024];
char g_szErrInfo[256];

int _tmain(int argc, _TCHAR* argv[])
{
	//////////////////////////////////////////////////////////////////////////////////

	cout << "\n";
	cout << "\n";
	cout << "\tTradeX完全兼容原有的Trade.dll下单业务，整合了行情API" << endl;
	cout << "\t解决了华泰等券商服务器无法正常连接的问题，在任何时间段都可以正确取数据" << endl;
	cout << "\t支持VC,VB，C#，Python，直连交易服务器和行情服务器" << endl;
	cout << "\n";
	cout << "\t如有需要，联系QQ：3048747297； 技术支持QQ群：318139137" << endl;
	cout << "\n";

	cout << "按回车键进行测试..." << endl;
	cin.get();

	cout << endl;
	cout << "\n";

	cout << "测试交易API, 按回车键继续...\n" << std::endl;

	//
	//

	cout << "1 - OpenTdx() ... ";
	OpenTdx();

	cout << "ok\n" << endl;
	cout << "\t按回车键继续......\n";

	//
	//

	cout << "2 - Logon(\"mock.tdx.com.cn\", 7708, \"6.40\", 9000, \"net828@163.com\", \"f001001001005792\", \"123123\", \"\", g_szErrInfo) ... ";

	int nClientID = Logon("mock.tdx.com.cn", 7708, "6.40", 9000, "net828@163.com","f001001001005792", "123123", "", g_szErrInfo);
	if (nClientID < 0)
	{
		cout << "fail" << endl;
		cout << "\t" << g_szErrInfo << endl;

		cin.get();

		return -1;
	}

	cout << "ok\n" << endl;

	cout << "\t按回车键继续......\n";
	cin.get();

	//
	//

	cout << "3 - QueryData\n" << endl;

	cout << "\t 0 - 查询资金 QueryData(nClientID, 0, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 0, g_szResult, g_szErrInfo);
	cout << "查询资金结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 1 - 查询股份     QueryData(nClientID, 1, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 1, g_szResult, g_szErrInfo);
	cout << "查询股份结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 2 - 查询当日委托 QueryData(nClientID, 2, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 2, g_szResult, g_szErrInfo);
	cout << "查询当日委托结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 3 - 查询当日成交 QueryData(nClientID, 3, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 3, g_szResult, g_szErrInfo);
	cout << "查询当日成交结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 4 - 查询可撤单   QueryData(nClientID, 4, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 4, g_szResult, g_szErrInfo);
	cout << "查询可撤单结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 5 - 查询股东代码 QueryData(nClientID, 5, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 5, g_szResult, g_szErrInfo);
	cout << "查询股东代码结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;
	cout << "\t按回车键继续......\n";
	cin.get();

	cout << "\t 6 - 查询融资余额 QueryData(nClientID, 6, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 6, g_szResult, g_szErrInfo);
	cout << "查询股东代码结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t 7 - 查询融券余额 QueryData(nClientID, 7, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 7, g_szResult, g_szErrInfo);
	cout << "查询融券余额结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << endl;

	cout << "\t按回车键继续......\n";
	cin.get();

	cout << "\t 8 - 查询可融证券 QueryData(nClientID, 8, g_szResult, g_szErrInfo)\n" << endl;
	QueryData(nClientID, 8, g_szResult, g_szErrInfo);
	cout << "查询可融证券结果:\n"<< g_szResult << " " << g_szErrInfo << endl;

	cout << "\t按回车键继续......\n";
	cin.get();

	//
	//

	cout << "4 - SendOrder(nClientID, 0, 0, \"A111111\", \"601988\", 2.7f, 100, g_szResult, g_szErrInfo) ... ";

	SendOrder(nClientID, 0, 0, "A111111", "601988", 2.7f, 100, g_szResult, g_szErrInfo);
	std::string sErrInfo = g_szErrInfo;
	if (sErrInfo.empty())
	{
	    cout << "ok\n" << endl;
	}
	else
	{
		cout << "fail\n" << endl;
		cout << "\t" << g_szErrInfo << endl;
	}

	cout << "\t按回车键继续......\n";
	cin.get();

	cout << "测试行情API, 按回车键继续...\n" << std::endl;

	test_hq_funcs("14.17.75.71", 7709);

	//
	//

	Logoff(nClientID);
	CloseTdx();

	cout << "测试结束!!!" << endl;
	cin.get();

	return 0;
}

