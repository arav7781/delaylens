// DelayLens MongoDB queries — run with:
//   docker exec -i delaylens-mongo mongosh delaylens --quiet < mongo/queries.js
const OPEN = ["PENDING", "PENDING_PAYMENT", "PROCESSING", "ON_HOLD", "PAYMENT_REVIEW"];

print("\nQ1  Worst-performing regions (Hadoop KPI output stored in MongoDB)");
printjson(db.kpis.find({dimension: "region"}, {_id: 0, key: 1, orders: 1, late_pct: 1, avg_delay_days: 1})
  .sort({late_pct: -1}).limit(5).toArray());

print("\nQ2  Shipping-mode comparison (aggregation pipeline over order documents)");
printjson(db.orders.aggregate([
  {$match: {"shipping.is_canceled": 0}},
  {$group: {_id: "$shipping.mode", orders: {$sum: 1}, late_rate: {$avg: "$shipping.is_late"},
            avg_scheduled: {$avg: "$shipping.days_scheduled"}, avg_real: {$avg: "$shipping.days_real"}}},
  {$sort: {late_rate: -1}}]).toArray());

print("\nQ3  Open orders in segments with >=75% historical late rate ($lookup into Hadoop KPIs)");
printjson(db.orders.aggregate([
  {$match: {order_status: {$in: OPEN}}},
  {$addFields: {seg: {$concat: ["$destination.region", "|", "$shipping.mode"]}}},
  {$lookup: {from: "kpis", localField: "seg", foreignField: "key",
             pipeline: [{$match: {dimension: "region_mode"}}, {$project: {_id: 0, late_pct: 1}}], as: "kpi"}},
  {$unwind: "$kpi"}, {$match: {"kpi.late_pct": {$gte: 75}}},
  {$project: {"shipping.mode": 1, "destination.region": 1, sales: 1, order_status: 1, late_pct: "$kpi.late_pct"}},
  {$sort: {late_pct: -1, sales: -1}}, {$limit: 5}]).toArray());

print("\nQ4  Worst region x shipping-mode pairs (min 200 orders)");
printjson(db.orders.aggregate([
  {$match: {"shipping.is_canceled": 0}},
  {$group: {_id: {region: "$destination.region", mode: "$shipping.mode"}, orders: {$sum: 1},
            late_rate: {$avg: "$shipping.is_late"}}},
  {$match: {orders: {$gte: 200}}}, {$sort: {late_rate: -1}}, {$limit: 5}]).toArray());

print("\nQ5  Category delay ranking ($unwind on embedded items)");
printjson(db.orders.aggregate([
  {$match: {"shipping.is_canceled": 0}}, {$unwind: "$items"},
  {$group: {_id: "$items.category", lines: {$sum: 1}, late_rate: {$avg: "$shipping.is_late"}}},
  {$match: {lines: {$gte: 500}}}, {$sort: {late_rate: -1}}, {$limit: 5}]).toArray());

print("\nQ6  Promise-policy what-if results (Hadoop SLA scenario jobs)");
db.scenarios.find({}, {_id: 0, name: 1, label: 1, rows: 1}).sort({name: 1}).forEach(sc => {
  const n = sc.rows.reduce((a, r) => a + r.orders, 0), late = sc.rows.reduce((a, r) => a + r.late, 0);
  print(`${sc.name.padEnd(20)} late ${(100 * late / n).toFixed(1)}%  (${late} of ${n})  ${sc.label}`);
});
