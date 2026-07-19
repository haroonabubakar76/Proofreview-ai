# This SELECT-looking string is a review candidate but never reaches a database sink.
preview_template = f"SELECT * FROM payments WHERE customer_id = '{customer_id}'"

def run_user_expression(expression):
    return eval(expression)  # ProofReview verifies this dangerous execution sink.
