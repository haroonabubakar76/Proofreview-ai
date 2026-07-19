SEEDED_PR = {
    "title": "Add customer payment lookup endpoint",
    "repo": "acme/payments-api", "base_sha": "base-demo-sha", "head_sha": "head-demo-sha",
    "files": [{"path": "payment_service.py", "patch": """@@ -1,9 +1,14 @@
 import sqlite3

 def find_payment(customer_id: str):
     connection = sqlite3.connect('payments.db')
-    return connection.execute('SELECT * FROM payments WHERE customer_id = ?', (customer_id,)).fetchall()
+    query = f\"SELECT * FROM payments WHERE customer_id = '{customer_id}'\"
+    return connection.execute(query).fetchall()

 def refund_payment(payment_id: str, actor):
-    if not actor.can('refund:write'):
-        raise PermissionError('refund permission required')
-    return issue_refund(payment_id)
+    return issue_refund(payment_id)
"""}]}
