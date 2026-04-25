# app/shipping_assist/records/__init__.py
"""
TMS / TransportRecords module shell.

语义定位：
- TransportRecords 负责 shipping_records（物流台帐）的读取入口
- 当前阶段 shipping_records 只保留“我方发货事实”
- 物流状态不再由本模块维护，不再提供状态写入口
"""
