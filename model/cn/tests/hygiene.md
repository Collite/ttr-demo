# Concept hygiene

84 concepts — 66 er-grounded · 11 md-grounded · 7 ungrounded

| Concept | Stereotype | Grade | Via | Grounding | Hop | Lands on | Open tier |
|---|---|---|---|---|---|---|---|
| cn.AbusiveReturner | phase | md-grounded | md-hop | — | — | er.entity.customer (← cn.Customer) | — |
| cn.BoughtHereLine | phase | er-grounded | direct | — | — | er.entity.return_request_line (← cn.ReturnLine) | — |
| cn.Channel | kind | er-grounded | direct | er.entity.sales.channel | — | er.entity.sales.channel | — |
| cn.Customer | role | md-grounded | md-hop | md.dimension.Customer | md.dimension.Customer → er.entity.customer | er.entity.customer | — |
| cn.CustomerPrice | event | er-grounded | direct | er.entity.customer_price | — | er.entity.customer_price | — |
| cn.DebtorCustomer | phase | md-grounded | md-hop | — | — | er.entity.customer (← cn.Customer) | — |
| cn.HeldOrder | phase | er-grounded | direct | — | — | er.entity.order (← cn.Order) | — |
| cn.InStockAtCenter | phase | er-grounded | direct | — | — | er.entity.return_request_line (← cn.ReturnLine) | — |
| cn.Inventory | event | er-grounded | direct | er.entity.inventory | — | er.entity.inventory | — |
| cn.Invoice | kind | er-grounded | direct | er.entity.invoice | — | er.entity.invoice | — |
| cn.Invoicing | event | er-grounded | direct | er.entity.invoice | — | er.entity.invoice | — |
| cn.Item | kind | md-grounded | md-hop | md.dimension.Product | md.dimension.Product → er.entity.item | er.entity.item | — |
| cn.LargeOrder | phase | er-grounded | direct | — | — | er.entity.order (← cn.Order) | — |
| cn.LateReturnLine | phase | er-grounded | direct | — | — | er.entity.return_request_line (← cn.ReturnLine) | — |
| cn.MarketplaceSale | phase | er-grounded | direct | — | — | er.entity.sales (← cn.Sale) | — |
| cn.MispricedLine | phase | er-grounded | direct | — | — | er.entity.sales_line (← cn.OrderLine) | — |
| cn.Order | event | er-grounded | direct | er.entity.order | — | er.entity.order | — |
| cn.OrderLine | event | er-grounded | direct | er.entity.sales_line | — | er.entity.sales_line | — |
| cn.OverdueInvoice | phase | er-grounded | direct | — | — | er.entity.invoice (← cn.Invoicing) | — |
| cn.PendingOrder | phase | er-grounded | direct | — | — | er.entity.order (← cn.Order) | — |
| cn.PlacedOrder | phase | er-grounded | direct | er.entity.placed_order | — | er.entity.placed_order | — |
| cn.PriceList | event | er-grounded | direct | er.entity.price_list | — | er.entity.price_list | — |
| cn.ReceivedReturnLine | phase | er-grounded | direct | — | — | er.entity.return_request_line (← cn.ReturnLine) | — |
| cn.Return | event | er-grounded | direct | er.entity.channel_returns | — | er.entity.channel_returns | — |
| cn.ReturnLine | event | er-grounded | direct | er.entity.return_request_line | — | er.entity.return_request_line | — |
| cn.ReturnReason | kind | md-grounded | md-hop | md.dimension.ReturnReason | md.dimension.ReturnReason → er.entity.reason | er.entity.reason | — |
| cn.ReturnRequest | event | er-grounded | direct | er.entity.return_request | — | er.entity.return_request | — |
| cn.Sale | event | er-grounded | direct | er.entity.sales | — | er.entity.sales | — |
| cn.ShortLine | phase | er-grounded | direct | — | — | er.entity.sales_line (← cn.OrderLine) | — |
| cn.SmallValueLine | phase | er-grounded | direct | — | — | er.entity.return_request_line (← cn.ReturnLine) | — |
| cn.Store | kind | md-grounded | md-hop | md.dimension.Store | md.dimension.Store → er.entity.store | er.entity.store | — |
| cn.StoreSale | phase | er-grounded | direct | — | — | er.entity.sales (← cn.Sale) | — |
| cn.Warehouse | kind | md-grounded | md-hop | md.dimension.DistributionCentre | md.dimension.DistributionCentre → er.entity.warehouse | er.entity.warehouse | — |
| cn.WarehouseOutage | event | er-grounded | direct | er.entity.warehouse_outage | — | er.entity.warehouse_outage | — |
| cn.WebSale | phase | er-grounded | direct | — | — | er.entity.sales (← cn.Sale) | — |
| cn.amount | quality | er-grounded | direct | er.entity.invoice.amount | — | er.entity.invoice.amount | — |
| cn.applicable_price | quality | ungrounded | — | — | — | — | — |
| cn.as_of_date | quality | er-grounded | direct | er.entity.inventory.as_of_date | — | er.entity.inventory.as_of_date | — |
| cn.center | quality | er-grounded | direct | er.entity.customer.center | — | er.entity.customer.center | — |
| cn.channel | quality | er-grounded | direct | er.entity.order.channel | — | er.entity.order.channel | — |
| cn.cp_from | quality | er-grounded | direct | er.entity.customer_price.valid_from | — | er.entity.customer_price.valid_from | — |
| cn.cp_price | quality | er-grounded | direct | er.entity.customer_price.price | — | er.entity.customer_price.price | — |
| cn.cp_to | quality | er-grounded | direct | er.entity.customer_price.valid_to | — | er.entity.customer_price.valid_to | — |
| cn.delivered_date | quality | er-grounded | direct | er.entity.order.delivered_date | — | er.entity.order.delivered_date | — |
| cn.due | quality | er-grounded | direct | er.entity.invoice.due | — | er.entity.invoice.due | — |
| cn.held_for | quality | er-grounded | direct | er.entity.order.held_for | — | er.entity.order.held_for | — |
| cn.invoice_status | quality | er-grounded | direct | er.entity.invoice.status | — | er.entity.invoice.status | — |
| cn.issued | quality | er-grounded | direct | er.entity.invoice.issued | — | er.entity.invoice.issued | — |
| cn.line_amount | quality | ungrounded | — | — | — | — | — |
| cn.line_date | quality | er-grounded | direct | er.entity.sales_line.sold_date | — | er.entity.sales_line.sold_date | — |
| cn.line_quantity | quality | er-grounded | direct | er.entity.sales_line.quantity | — | er.entity.sales_line.quantity | — |
| cn.line_state | quality | er-grounded | direct | er.entity.return_request_line.state | — | er.entity.return_request_line.state | — |
| cn.line_value | quality | er-grounded | direct | er.entity.sales_line.ext_sales_price | — | er.entity.sales_line.ext_sales_price | — |
| cn.on_hand | quality | ungrounded | — | — | — | — | — |
| cn.open_amount | quality | ungrounded | — | — | — | — | — |
| cn.order_value | quality | er-grounded | direct | er.entity.order.value | — | er.entity.order.value | — |
| cn.outage | quality | ungrounded | — | — | — | — | — |
| cn.outage_from | quality | er-grounded | direct | er.entity.warehouse_outage.from_date | — | er.entity.warehouse_outage.from_date | — |
| cn.outage_reason | quality | er-grounded | direct | er.entity.warehouse_outage.reason | — | er.entity.warehouse_outage.reason | — |
| cn.outage_to | quality | er-grounded | direct | er.entity.warehouse_outage.to_date | — | er.entity.warehouse_outage.to_date | — |
| cn.paid | quality | er-grounded | direct | er.entity.invoice.paid | — | er.entity.invoice.paid | — |
| cn.pl_channel | quality | er-grounded | direct | er.entity.price_list.channel | — | er.entity.price_list.channel | — |
| cn.pl_from | quality | er-grounded | direct | er.entity.price_list.valid_from | — | er.entity.price_list.valid_from | — |
| cn.pl_price | quality | er-grounded | direct | er.entity.price_list.price | — | er.entity.price_list.price | — |
| cn.pl_to | quality | er-grounded | direct | er.entity.price_list.valid_to | — | er.entity.price_list.valid_to | — |
| cn.placed_date | quality | er-grounded | direct | er.entity.order.placed_date | — | er.entity.order.placed_date | — |
| cn.quantity | quality | md-grounded | md-hop | md.measure.quantity | md.measure.quantity → er.entity.sales.quantity | er.entity.sales.quantity | — |
| cn.quantity_on_hand | quality | er-grounded | direct | er.entity.inventory.quantity_on_hand | — | er.entity.inventory.quantity_on_hand | — |
| cn.request_state | quality | er-grounded | direct | er.entity.return_request.state | — | er.entity.return_request.state | — |
| cn.requested_date | quality | er-grounded | direct | er.entity.return_request.requested_date | — | er.entity.return_request.requested_date | — |
| cn.requested_resolution | quality | er-grounded | direct | er.entity.return_request_line.requested_resolution | — | er.entity.return_request_line.requested_resolution | — |
| cn.return_amount | quality | md-grounded | md-hop | md.measure.returnAmount | md.measure.returnAmount → er.entity.channel_returns.return_amt | er.entity.channel_returns.return_amt | — |
| cn.return_quantity | quality | er-grounded | direct | er.entity.return_request_line.quantity | — | er.entity.return_request_line.quantity | — |
| cn.return_reason | quality | er-grounded | direct | er.entity.return_request_line.reason | — | er.entity.return_request_line.reason | — |
| cn.return_share | quality | ungrounded | — | — | — | — | — |
| cn.return_unit_price | quality | er-grounded | direct | er.entity.return_request_line.unit_price | — | er.entity.return_request_line.unit_price | — |
| cn.returned_date | quality | er-grounded | direct | er.entity.channel_returns.returned_date | — | er.entity.channel_returns.returned_date | — |
| cn.returned_quantity | quality | md-grounded | md-hop | md.measure.quantity | md.measure.quantity → er.entity.channel_returns.return_quantity | er.entity.channel_returns.return_quantity | — |
| cn.revenue | quality | md-grounded | md-hop | md.measure.revenue | md.measure.revenue → er.entity.sales.ext_sales_price | er.entity.sales.ext_sales_price | — |
| cn.short | quality | ungrounded | — | — | — | — | — |
| cn.sold_date | quality | er-grounded | direct | er.entity.sales.sold_date | — | er.entity.sales.sold_date | — |
| cn.state | quality | er-grounded | direct | er.entity.order.state | — | er.entity.order.state | — |
| cn.unit_price | quality | er-grounded | direct | er.entity.sales_line.unit_price | — | er.entity.sales_line.unit_price | — |
| cn.way | quality | er-grounded | direct | er.entity.return_request_line.way | — | er.entity.return_request_line.way | — |

Open-tier relation types: none.

## Dangling groundings

None.

## Redundant term duplicates

None.

## Phase as default sense

None.

## Retired codes

None — checked once vocabulary versions register (CN-P5 S5.3).

## Definitions

- cn.AbusiveReturner — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:70: the definition cannot render on md: `ReturnLine`, `ReturnRequest`, `line_state`, `OrderLine`, `line_value`, `return_quantity`, `return_unit_price` have no md grounding and no md element hops to their E-R landing
- cn.BoughtHereLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:57: the definition cannot render on md: `OrderLine`, `ReturnLine`, `ReturnRequest`, `Order` have no md grounding and no md element hops to their E-R landing
- cn.DebtorCustomer — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:44: the definition cannot render on md: `Invoicing`, `invoice_status` have no md grounding and no md element hops to their E-R landing
- cn.HeldOrder — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:17: the definition cannot render on md: `state` has no md grounding and no md element hops to its E-R landing
- cn.InStockAtCenter — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:81: the definition cannot render on md: `ReturnLine`, `center`, `as_of_date`, `return_quantity` have no md grounding and no md element hops to their E-R landing
- cn.LargeOrder — cn/definition-unreachable(md) (hygiene) at model/cn/concepts.ttrm:121: the definition cannot render on md: `order_value` has no md grounding and no md element hops to its E-R landing
- cn.LateReturnLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:65: the definition cannot render on md: `ReturnLine`, `ReturnRequest`, `Order` have no md grounding and no md element hops to their E-R landing
- cn.MarketplaceSale — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:13: the definition cannot render on md: `Sale`, `Channel` have no md grounding and no md element hops to their E-R landing
- cn.MispricedLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:33: the definition cannot render on md: `unit_price`, `CustomerPrice`, `OrderLine`, `Order`, `cp_price`, `PriceList`, `pl_channel`, `channel`, `pl_price` have no md grounding and no md element hops to their E-R landing
- cn.OverdueInvoice — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:39: the definition cannot render on md: `invoice_status`, `Invoicing` have no md grounding and no md element hops to their E-R landing
- cn.PendingOrder — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:16: the definition cannot render on md: `state` has no md grounding and no md element hops to its E-R landing
- cn.ReceivedReturnLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:51: the definition cannot render on md: `line_state` has no md grounding and no md element hops to its E-R landing
- cn.ShortLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:27: the definition cannot render on md: `line_quantity`, `WarehouseOutage`, `OrderLine`, `as_of_date` have no md grounding and no md element hops to their E-R landing
- cn.SmallValueLine — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:75: the definition cannot render on md: `return_quantity`, `return_unit_price` have no md grounding and no md element hops to their E-R landing
- cn.StoreSale — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:11: the definition cannot render on md: `Sale`, `Channel` have no md grounding and no md element hops to their E-R landing
- cn.WebSale — cn/definition-unreachable(md) (hygiene) at model/cn/phases.ttrm:12: the definition cannot render on md: `Sale`, `Channel` have no md grounding and no md element hops to their E-R landing
- cn.applicable_price — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:102: the definition cannot render on md: `CustomerPrice`, `OrderLine`, `Order`, `cp_price`, `PriceList`, `pl_channel`, `channel`, `pl_price` have no md grounding and no md element hops to their E-R landing
- cn.line_amount — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:110: the definition cannot render on md: `return_quantity`, `return_unit_price` have no md grounding and no md element hops to their E-R landing
- cn.on_hand — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:84: the definition cannot render on md: `OrderLine`, `as_of_date` have no md grounding and no md element hops to their E-R landing
- cn.open_amount — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:78: the definition cannot render on md: `amount`, `paid` have no md grounding and no md element hops to their E-R landing
- cn.outage — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:95: the definition cannot render on md: `WarehouseOutage`, `OrderLine` have no md grounding and no md element hops to their E-R landing
- cn.return_share — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:117: the definition cannot render on md: `ReturnLine`, `ReturnRequest`, `line_state`, `OrderLine`, `line_value`, `return_quantity`, `return_unit_price` have no md grounding and no md element hops to their E-R landing
- cn.short — cn/definition-unreachable(md) (hygiene) at model/cn/qualities.ttrm:89: the definition cannot render on md: `line_quantity`, `OrderLine`, `as_of_date` have no md grounding and no md element hops to their E-R landing
