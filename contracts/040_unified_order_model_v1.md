# 040 统一订单模型 v1（字段字典）

> 统一定义外部平台订单到内部系统的映射，作为 170_* 契约的基础模型。

## 表：order（订单头）

- **幂等键**：`external_order_no`
- **派生键**：`order_id`
- **状态模型**：`status`（created/paid/allocated/shipped/closed/...）
- **支付模型**：`pay_status`（unpaid/paid/refunding/refunded/partial_refund）
- **金额字段**：`amount_*` 采用两位小数，CNY 默认。

字段 | 类型 | 必填 | 默认值 | 枚举 | 说明
---|---|---|---|---|---
order_id | string | YES |  |  | 统一订单ID（平台订单号或UUID）
platform | string | YES |  | pdd,taobao,jd,douyin,wx,manual | 来源平台
shop_id | string | YES |  |  | 店铺ID（平台内标识）
external_order_no | string | YES |  |  | 平台原始订单号（幂等键之一）
status | string | YES | created | created,paid,allocated,shipped,closed,cancelled,refunded,partial_refund | 订单状态
pay_status | string | YES | unpaid | unpaid,paid,refunding,refunded,partial_refund | 支付状态
currency | string | NO | CNY |  | 币种
amount_goods | decimal(18,2) | YES | 0.00 |  | 商品金额（不含运费）
amount_total | decimal(18,2) | YES | 0.00 |  | 应付总额
address_name | string | YES |  |  | 收件人姓名
address_phone | string | YES |  |  | 收件人电话
address_province | string | YES |  |  | 省
address_city | string | YES |  |  | 市
address_detail | string | YES |  |  | 详细地址

---

## 表：order_item（订单行）

字段 | 类型 | 必填 | 默认值 | 枚举 | 说明
---|---|---|---|---|---
order_id | string | YES |  |  | 关联统一订单ID
line_no | int | YES |  |  | 行号
sku | string | YES |  |  | 内部SKU编码
qty | int | YES | 1 |  | 数量
price | decimal(18,2) | YES | 0.00 |  | 单价（未折扣）
amount | decimal(18,2) | YES | 0.00 |  | 行实付
