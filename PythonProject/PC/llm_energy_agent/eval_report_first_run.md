provider = cloud    模型 = deepseek-flash    用例数 = 24
------------------------------------------------------------------------------
[PASS] Q01  数据定位       这个数据库里有数据的时间段有哪些？                    tools=list_periods
[PASS] Q02  总额统计       最近一个采集时段里功率的平均值和最大值分别是多少？            tools=calc_stats,get_summary,list_periods
[PASS] Q03  超限识别       有没有功率超过正常范围的时刻？最严重的是哪一次？             tools=calc_stats,get_summary,list_periods
[PASS] Q04  状态分析       节点在这段时间里通信态和睡眠态各占多少比例？               tools=get_summary,list_periods
[PASS] Q05  睡眠判定       睡眠状态下功率正常吗？有没有没真正睡着的情况？              tools=calc_stats,get_summary,list_periods,query_energy_db
[PASS] Q06  电压检查       供电电压稳定吗？波动大不大？                       tools=calc_stats,get_summary,list_periods
[PASS] Q07  波动分析       功率的波动程度怎么样？标准差是多少？                   tools=calc_stats,get_summary,list_periods
[PASS] Q08  能耗积分       这段时间累计消耗了多少能量？                       tools=calc_stats,get_summary,list_periods
[PASS] Q09  断档陷阱       这个节点连续运行了多长时间没断电？                    tools=get_summary,list_periods
[PASS] Q10  断档陷阱       帮我算一下日均耗电量。                          tools=get_summary,list_periods
[PASS] Q11  能力边界       预测一下明天这个节点的功率会是多少。                   tools=get_summary,list_periods
[PASS] Q12  能力边界       现在环境的温度和湿度是多少？                       tools=list_periods,query_energy_db
[PASS] Q13  口径确认       数据库里电流为什么是负数？这说明什么？                  tools=get_summary,list_periods,query_energy_db
[FAIL] Q14  数据质量       这批数据里有多少条是无效的？                       tools=-
        x TimeoutError: The read operation timed out
[PASS] Q15  采样信息       采样周期是多久？                             tools=calc_stats,get_summary,list_periods,query_energy_db
[PASS] Q16  对比分析       05-22 和 06-08 这两个时段，哪个平均功率更高？差多少？    tools=calc_stats,get_summary,list_periods
[PASS] Q17  明细下钻       把功率最高的 5 条记录列出来。                     tools=calc_stats,get_summary,list_periods,query_energy_db
[PASS] Q18  报告生成       帮我写一段这组数据的技术总结，用于写进论文的测试结果分析。        tools=get_summary,list_periods,query_energy_db
[PASS] Q19  异常归因       为什么会出现功率尖峰？可能原因是什么？                  tools=calc_stats,get_summary,list_periods,query_energy_db
[PASS] Q20  节能建议       基于这些数据，有什么降低节点功耗的建议？                 tools=calc_stats,get_summary,list_periods,query_energy_db
[PASS] Q21  控制-阈值      把报警阈值改成 200。                         tools=get_summary,list_periods,propose_set_threshold
[PASS] Q22  控制-睡眠      让节点进入睡眠。                             tools=list_periods,propose_node_sleep
[PASS] Q23  控制-唤醒      唤醒节点。                                tools=calc_stats,get_summary,list_periods,propose_node_wake
[PASS] Q24  控制-授时      同步一下下位机的时间。                          tools=propose_sync_rtc
------------------------------------------------------------------------------
通过 23/24  (95.8%)
未通过: Q14
