import logging
from rag_pipeline import run_fact_check_pipeline

logging.basicConfig(level=logging.INFO)
print("Starting run_fact_check_pipeline")
result = run_fact_check_pipeline(input_text="chitra is miss universe in 2026")
print("Result:")
print(result)
