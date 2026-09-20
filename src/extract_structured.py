import json
import re

def extract_structured_data():
    with open('raw/scraped_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    structured_data = []

    for item in data:
        content = item['content']
        fund_name = item['metadata']['fund_name']

        # Regex extraction based on the \n formatting in the scraped text
        expense_ratio = re.search(r'Expense ratio \n (.*?)\n', content)
        exit_load = re.search(r'Exit load \n (.*?)\n', content)
        min_sip = re.search(r'Min\. for SIP \n (.*?)\n', content)
        nav = re.search(r'NAV:.*? \n (.*?)\n', content)
        benchmark = re.search(r'Fund benchmark \n (.*?)\n', content)
        investment_objective = re.search(r'Investment Objective \n (.*?)\n', content)

        structured_data.append({
            "fund_name": fund_name,
            "expense_ratio": expense_ratio.group(1).strip() if expense_ratio else "Not Found",
            "exit_load": exit_load.group(1).strip() if exit_load else "Not Found",
            "minimum_sip": min_sip.group(1).strip() if min_sip else "Not Found",
            "nav": nav.group(1).strip() if nav else "Not Found",
            "benchmark": benchmark.group(1).strip() if benchmark else "Not Found",
            "investment_objective": investment_objective.group(1).strip() if investment_objective else "Not Found"
        })

    with open('raw/structured_data.json', 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=4, ensure_ascii=False)
    
    print("Successfully extracted key-value pairs into raw/structured_data.json!")

if __name__ == "__main__":
    extract_structured_data()
