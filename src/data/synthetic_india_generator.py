"""
Sentinel AI — Custom Synthetic India Dataset Generator

Generates ~10,000 synthetic transactions along with supporting entities:
- Customers (1,200)
- Accounts (1,500)
- Devices (1,400)
- Beneficiaries (2,000)
- Transactions Features (10,000)
- Transactions Targets (10,000)
- Graph Edges for Neo4j (10,000)

Guarantees:
- 100% Synthetic, zero real PII
- Deterministic reproducibility via configurable seed (default 42)
- Strict relational integrity and balance arithmetic
- Zero target label leakage into ML feature vectors
"""

import os
import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd


# Indian Reference Data for Synthetic Generation
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Shaurya", "Rohan", "Ananya", "Diya", "Sanya", "Priya", "Neha", "Pooja", "Aditi", "Kavya",
    "Rajesh", "Suresh", "Ramesh", "Sunil", "Anil", "Vikram", "Sanjay", "Deepak", "Amit", "Rahul",
    "Priya", "Sunita", "Anita", "Geeta", "Meena", "Seema", "Rekha", "Shoba", "Lata", "Usha"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Patel", "Mehta", "Shah", "Joshi", "Rao", "Nair", "Pillai",
    "Kumar", "Singh", "Das", "Mukherjee", "Banerjee", "Chatterjee", "Reddy", "Chowdhury", "Deshmukh", "Kulkarni",
    "Bhat", "Hegde", "Shetty", "Gowda", "Naidu", "Menon", "Kapoor", "Khanna", "Malhotra", "Saxena"
]

CITIES = [
    {"city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "long": 72.8777},
    {"city": "Delhi", "state": "Delhi", "lat": 28.7041, "long": 77.1025},
    {"city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "long": 77.5946},
    {"city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "long": 78.4867},
    {"city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "long": 80.2707},
    {"city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "long": 88.3639},
    {"city": "Pune", "state": "Maharashtra", "lat": 18.5204, "long": 73.8567},
    {"city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "long": 72.5714},
    {"city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "long": 75.7873},
    {"city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "long": 80.9462},
    {"city": "Patna", "state": "Bihar", "lat": 25.5941, "long": 85.1376},
    {"city": "Guwahati", "state": "Assam", "lat": 26.1445, "long": 91.7362},
    {"city": "Kochi", "state": "Kerala", "lat": 9.9312, "long": 76.2673}
]

BANK_IFSC_PREFIXES = ["SBIN000", "HDFC000", "ICIC000", "AXIS000", "PUNB000", "BOB000"]
UPI_HANDLES = ["@oksbi", "@okicici", "@paytm", "@ybl", "@axisbank", "@barodampay"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate geodesic distance between two lat/long points in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class SyntheticIndiaDatasetGenerator:
    """
    Deterministic programmatic generator for Sentinel AI Custom Synthetic India Dataset.
    """

    def __init__(self, seed: int = 42, num_transactions: int = 10000):
        self.seed = seed
        self.num_transactions = num_transactions
        self.anchor_date = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        self.end_date = self.anchor_date + timedelta(days=30)
        
        # Reset seeds
        random.seed(self.seed)
        np.random.seed(self.seed)

        # Entity DataFrames
        self.customers_df = pd.DataFrame()
        self.accounts_df = pd.DataFrame()
        self.devices_df = pd.DataFrame()
        self.beneficiaries_df = pd.DataFrame()
        self.tx_features_df = pd.DataFrame()
        self.tx_targets_df = pd.DataFrame()
        self.graph_edges_df = pd.DataFrame()

    def _set_seeds(self):
        random.seed(self.seed)
        np.random.seed(self.seed)

    def generate_all(self) -> Dict[str, pd.DataFrame]:
        """Execute full entity generation pipeline."""
        self._set_seeds()
        
        # 1. Customers (1,200)
        customers = self._generate_customers(count=1200)
        self.customers_df = pd.DataFrame(customers)

        # 2. Accounts (1,500)
        accounts = self._generate_accounts(self.customers_df, count=1500)
        self.accounts_df = pd.DataFrame(accounts)

        # 3. Devices (1,400)
        devices = self._generate_devices(self.customers_df, count=1400)
        self.devices_df = pd.DataFrame(devices)

        # 4. Beneficiaries (2,000)
        beneficiaries = self._generate_beneficiaries(self.accounts_df, count=2000)
        self.beneficiaries_df = pd.DataFrame(beneficiaries)

        # 5. Transactions & Ground Truth Targets (10,000)
        tx_features, tx_targets, graph_edges = self._generate_transactions(
            self.customers_df, self.accounts_df, self.devices_df, self.beneficiaries_df, self.num_transactions
        )

        self.tx_features_df = pd.DataFrame(tx_features)
        self.tx_targets_df = pd.DataFrame(tx_targets)
        self.graph_edges_df = pd.DataFrame(graph_edges)

        return {
            "customers": self.customers_df,
            "accounts": self.accounts_df,
            "devices": self.devices_df,
            "beneficiaries": self.beneficiaries_df,
            "transactions_features": self.tx_features_df,
            "transactions_targets": self.tx_targets_df,
            "graph_edges": self.graph_edges_df
        }

    def _generate_customers(self, count: int = 1200) -> List[Dict[str, Any]]:
        customers = []
        for i in range(1, count + 1):
            cust_id = f"CUST_IND_{i:06d}"
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            name = f"{fn} {ln}"
            
            # Customer Type
            rand_val = random.random()
            if rand_val < 0.875:
                cust_type = "INDIVIDUAL"
                declared_income = float(np.random.lognormal(mean=12.5, sigma=0.8)) # ~ ₹2.5L - ₹15L
            elif rand_val < 0.958:
                cust_type = "SOLE_PROPRIETORSHIP"
                declared_income = float(np.random.lognormal(mean=14.0, sigma=1.0)) # ~ ₹10L - ₹50L
            else:
                cust_type = "CORPORATE"
                declared_income = float(np.random.lognormal(mean=16.0, sigma=1.2)) # ~ ₹50L - ₹5Cr

            # Location
            loc = random.choice(CITIES)
            
            # KYC & PEP
            kyc_status = random.choices(["VERIFIED", "PENDING", "RE_KYC_DUE"], weights=[0.92, 0.05, 0.03])[0]
            pep_flag = 1 if random.random() < 0.012 else 0

            # Creation date between 1 to 5 years before simulation anchor
            days_ago = random.randint(365, 1825)
            creation_date = (self.anchor_date - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            customers.append({
                "customer_id": cust_id,
                "customer_name_synthetic": name,
                "customer_type": cust_type,
                "kyc_status": kyc_status,
                "pep_flag": pep_flag,
                "declared_annual_income_inr": round(declared_income, 2),
                "home_city": loc["city"],
                "home_state": loc["state"],
                "home_lat": loc["lat"],
                "home_long": loc["long"],
                "customer_creation_date": creation_date
            })
        return customers

    def _generate_accounts(self, customers_df: pd.DataFrame, count: int = 1500) -> List[Dict[str, Any]]:
        accounts = []
        cust_ids = customers_df["customer_id"].tolist()
        cust_creation_dict = dict(zip(customers_df["customer_id"], customers_df["customer_creation_date"]))
        cust_type_dict = dict(zip(customers_df["customer_id"], customers_df["customer_type"]))

        for i in range(1, count + 1):
            acc_id = f"ACC_IND_{i:06d}"
            # Ensure every customer gets at least 1 account, then random assignment
            if i <= len(cust_ids):
                cid = cust_ids[i - 1]
            else:
                cid = random.choice(cust_ids)

            acc_num = f"SYN99{random.randint(1000000000, 9999999999)}"
            ifsc = f"{random.choice(BANK_IFSC_PREFIXES)}{random.randint(1000, 9999)}"
            
            ctype = cust_type_dict[cid]
            if ctype == "CORPORATE":
                acc_type = "CURRENT"
            elif ctype == "SOLE_PROPRIETORSHIP":
                acc_type = random.choice(["CURRENT", "SAVINGS"])
            else:
                acc_type = random.choices(["SAVINGS", "SALARY", "MULE_SUSPECT"], weights=[0.85, 0.12, 0.03])[0]

            # Account opening date on or after customer creation date
            c_date = datetime.strptime(cust_creation_dict[cid], "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            days_after = random.randint(0, 180)
            open_dt = c_date + timedelta(days=days_after)
            open_date_str = open_dt.strftime("%Y-%m-%d")

            age_days = (self.anchor_date - open_dt).days

            # Baseline balances
            if acc_type == "CURRENT":
                init_balance = float(np.random.lognormal(mean=13.0, sigma=1.0))
            elif acc_type == "MULE_SUSPECT":
                init_balance = float(random.uniform(500.0, 5000.0))
            else:
                init_balance = float(np.random.lognormal(mean=10.5, sigma=1.0))

            hist_30d_avg_bal = round(init_balance * random.uniform(0.8, 1.2), 2)
            hist_30d_avg_tx = round(init_balance * random.uniform(0.05, 0.25), 2)
            hist_30d_tx_cnt = random.randint(5, 60)

            accounts.append({
                "account_id": acc_id,
                "customer_id": cid,
                "account_number_synthetic": acc_num,
                "ifsc_code_synthetic": ifsc,
                "account_type": acc_type,
                "account_open_date": open_date_str,
                "account_age_days": max(1, age_days),
                "current_balance_inr": round(init_balance, 2),
                "historical_30d_avg_balance_inr": hist_30d_avg_bal,
                "historical_30d_avg_tx_amt_inr": max(100.0, hist_30d_avg_tx),
                "historical_30d_tx_count": hist_30d_tx_cnt
            })
        return accounts

    def _generate_devices(self, customers_df: pd.DataFrame, count: int = 1400) -> List[Dict[str, Any]]:
        devices = []
        cust_ids = customers_df["customer_id"].tolist()
        
        for i in range(1, count + 1):
            dev_id = f"DEV_IND_{i:06d}"
            if i <= len(cust_ids):
                cid = cust_ids[i - 1]
            else:
                cid = random.choice(cust_ids)

            fpg = f"FPG_{random.getrandbits(64):016x}"
            dtype = random.choices(["ANDROID_MOBILE", "IOS_MOBILE", "WEB_BROWSER"], weights=[0.65, 0.25, 0.10])[0]
            os_ver = "Android 13" if dtype == "ANDROID_MOBILE" else ("iOS 17" if dtype == "IOS_MOBILE" else "Chrome 122")
            app_ver = f"v4.{random.randint(1, 9)}.{random.randint(0, 5)}"

            # First seen
            days_ago = random.randint(10, 300)
            first_seen = (self.anchor_date - timedelta(days=days_ago)).isoformat()
            is_reg = 1 if random.random() < 0.94 else 0
            assoc_cnt = random.choices([1, 2, 3, 5], weights=[0.88, 0.08, 0.03, 0.01])[0]

            devices.append({
                "device_id": dev_id,
                "customer_id": cid,
                "device_fingerprint_synthetic": fpg,
                "device_type": dtype,
                "os_version": os_ver,
                "app_version": app_ver,
                "first_seen_timestamp": first_seen,
                "is_registered": is_reg,
                "associated_accounts_count": assoc_cnt
            })
        return devices

    def _generate_beneficiaries(self, accounts_df: pd.DataFrame, count: int = 2000) -> List[Dict[str, Any]]:
        beneficiaries = []
        acc_ids = accounts_df["account_id"].tolist()

        for i in range(1, count + 1):
            ben_id = f"BEN_IND_{i:06d}"
            sender_acc = random.choice(acc_ids)
            receiver_acc = random.choice([a for a in acc_ids if a != sender_acc])

            vpa_handle = f"user{random.randint(100, 999)}{random.choice(UPI_HANDLES)}"
            days_ago = random.randint(1, 180)
            added_dt = self.anchor_date - timedelta(days=days_ago)

            status = random.choices(["ACTIVE", "COOLING_OFF", "BLOCKED"], weights=[0.95, 0.04, 0.01])[0]
            prior_cnt = random.randint(0, 25)

            beneficiaries.append({
                "beneficiary_id": ben_id,
                "sender_account_id": sender_acc,
                "receiver_account_id": receiver_acc,
                "receiver_vpa_synthetic": vpa_handle,
                "beneficiary_added_timestamp": added_dt.isoformat(),
                "beneficiary_status": status,
                "prior_tx_count": prior_cnt
            })
        return beneficiaries

    def _generate_transactions(self, customers_df: pd.DataFrame, accounts_df: pd.DataFrame, 
                              devices_df: pd.DataFrame, beneficiaries_df: pd.DataFrame, 
                              count: int = 10000) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        tx_features = []
        tx_targets = []
        graph_edges = []

        # Convert entity dataframes to quick lookup dicts
        acc_map = accounts_df.set_index("account_id").to_dict(orient="index")
        cust_map = customers_df.set_index("customer_id").to_dict(orient="index")
        dev_map = devices_df.set_index("device_id").to_dict(orient="index")

        # Map customer to their primary account and device
        cust_accounts = accounts_df.groupby("customer_id")["account_id"].apply(list).to_dict()
        cust_devices = devices_df.groupby("customer_id")["device_id"].apply(list).to_dict()
        all_accounts = accounts_df["account_id"].tolist()

        # Track account balances dynamically
        realtime_balances = {acc_id: acc_data["current_balance_inr"] for acc_id, acc_data in acc_map.items()}

        # Scenario quotas for 10,000 transactions
        # Legitimate: 8,200 | Borderline/Fraud: 1,800
        scenario_counts = {
            "SCENARIO_1_NORMAL_LEGITIMATE": 8200,
            "SCENARIO_2_HIGH_VALUE_SPIKE": 200,
            "SCENARIO_3_RAPID_BURST": 150,
            "SCENARIO_4_NEW_BENEFICIARY_LARGE_TX": 150,
            "SCENARIO_5_NEW_DEVICE_SUSPICIOUS": 150,
            "SCENARIO_6_STRUCTURING_SPLITTING": 150,
            "SCENARIO_7_LAYERING_NETWORK": 200,
            "SCENARIO_8_MULE_PASS_THROUGH": 200,
            "SCENARIO_9_FRAUD_RING_HUB": 200,
            "SCENARIO_10_IMPOSSIBLE_TRAVEL": 150,
            "SCENARIO_11_SHARED_DEVICE_IP": 150,
            "SCENARIO_12_MIXED_BORDERLINE_TRAVEL": 100
        }

        # Build execution sequence of scenarios
        scenario_queue = []
        for sc_id, sc_cnt in scenario_counts.items():
            scenario_queue.extend([sc_id] * sc_cnt)
        random.shuffle(scenario_queue)

        tx_counter = 1

        for idx, scenario in enumerate(scenario_queue):
            tx_id = f"TXN_IND_202608_{tx_counter:06d}"
            
            # Select random timestamp within 30-day window
            day_offset = random.randint(0, 29)
            
            # Diurnal weighting: 85% daytime (08:00 - 22:00), 15% night
            if random.random() < 0.85:
                hour = random.randint(8, 21)
            else:
                hour = random.choice([22, 23, 0, 1, 2, 3, 4, 5, 6, 7])
            
            minute = random.randint(0, 59)
            second = random.randint(0, 59)

            tx_dt = self.anchor_date + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)
            tx_timestamp_str = tx_dt.isoformat()

            # Select Sender & Receiver Accounts
            sender_acc_id = random.choice(all_accounts)
            receiver_acc_id = random.choice([a for a in all_accounts if a != sender_acc_id])

            sender_cust_id = acc_map[sender_acc_id]["customer_id"]
            receiver_cust_id = acc_map[receiver_acc_id]["customer_id"]
            sender_cust = cust_map[sender_cust_id]

            # Device selection
            sender_devs = cust_devices.get(sender_cust_id, [devices_df["device_id"].iloc[0]])
            dev_id = random.choice(sender_devs)

            # Location calculation
            home_lat = sender_cust["home_lat"]
            home_long = sender_cust["home_long"]

            # Scenario specifics logic
            is_fraud = 0
            risk_label = "LEGITIMATE"
            is_flagged_alert = 0

            # Default channel & amount sampling
            channel = random.choices(["UPI", "NEFT", "RTGS"], weights=[0.70, 0.22, 0.08])[0]
            
            if channel == "UPI":
                amount = round(float(np.random.lognormal(mean=7.0, sigma=1.2)), 2) # ~ ₹50 - ₹15,000
                amount = min(amount, 99999.00) # NPCI UPI cap
                amount = max(amount, 10.00)
            elif channel == "NEFT":
                amount = round(float(np.random.lognormal(mean=10.0, sigma=1.2)), 2) # ~ ₹5,000 - ₹2,00,000
                amount = max(amount, 500.00)
            else: # RTGS
                amount = round(float(np.random.lognormal(mean=14.0, sigma=0.8)), 2) # ~ ₹3L - ₹50L
                amount = max(amount, 200000.00) # Mandatory RBI RTGS minimum ₹2,00,000

            # Apply Scenario Configurations
            if scenario == "SCENARIO_1_NORMAL_LEGITIMATE":
                is_fraud = 0
                risk_label = "LEGITIMATE"
                is_flagged_alert = 0
                dist_km = round(random.uniform(0.1, 15.0), 2)
                is_new_dev = 1 if random.random() < 0.15 else 0
                is_new_ben = 1 if random.random() < 0.20 else 0
                ben_added_min = random.randint(1440, 43200)

            elif scenario == "SCENARIO_2_HIGH_VALUE_SPIKE":
                amount = round(acc_map[sender_acc_id]["historical_30d_avg_tx_amt_inr"] * random.uniform(8.0, 15.0), 2)
                if channel == "UPI":
                    amount = min(amount, 99999.00)
                if random.random() < 0.5:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1
                dist_km = round(random.uniform(1.0, 50.0), 2)
                is_new_dev = 0
                is_new_ben = 0
                ben_added_min = random.randint(2880, 20000)

            elif scenario == "SCENARIO_3_RAPID_BURST":
                amount = round(random.uniform(2000.0, 8000.0), 2)
                channel = "UPI"
                if random.random() < 0.33:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1
                dist_km = round(random.uniform(0.5, 10.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(5, 25)

            elif scenario == "SCENARIO_4_NEW_BENEFICIARY_LARGE_TX":
                channel = "NEFT"
                amount = round(random.uniform(150000.0, 450000.0), 2)
                is_new_ben = 1 if random.random() < 0.90 else 0
                ben_added_min = random.randint(2, 28)
                is_new_dev = 0
                dist_km = round(random.uniform(2.0, 20.0), 2)
                if random.random() < 0.33:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1

            elif scenario == "SCENARIO_5_NEW_DEVICE_SUSPICIOUS":
                channel = "UPI"
                amount = round(random.uniform(40000.0, 95000.0), 2)
                is_new_dev = 1 if random.random() < 0.88 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(10, 60)
                dist_km = round(random.uniform(100.0, 500.0), 2)
                if random.random() < 0.33:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1

            elif scenario == "SCENARIO_6_STRUCTURING_SPLITTING":
                channel = random.choice(["UPI", "NEFT"])
                amount = round(random.choice([49500.0, 49900.0, 98500.0, 99500.0]), 2)
                is_fraud = 1
                risk_label = "FRAUDULENT"
                is_flagged_alert = 1
                dist_km = round(random.uniform(5.0, 30.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(15, 120)

            elif scenario == "SCENARIO_7_LAYERING_NETWORK":
                channel = "RTGS" if random.random() < 0.5 else "NEFT"
                amount = round(random.uniform(300000.0, 1200000.0), 2)
                is_fraud = 1
                risk_label = "FRAUDULENT"
                is_flagged_alert = 1
                dist_km = round(random.uniform(10.0, 150.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(5, 45)

            elif scenario == "SCENARIO_8_MULE_PASS_THROUGH":
                channel = "UPI"
                amount = round(random.uniform(15000.0, 75000.0), 2)
                is_fraud = 1
                risk_label = "FRAUDULENT"
                is_flagged_alert = 1
                dist_km = round(random.uniform(20.0, 200.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(10, 90)

            elif scenario == "SCENARIO_9_FRAUD_RING_HUB":
                channel = "UPI"
                amount = round(random.uniform(25000.0, 85000.0), 2)
                is_fraud = 1
                risk_label = "FRAUDULENT"
                is_flagged_alert = 1
                dist_km = round(random.uniform(50.0, 400.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(15, 180)

            elif scenario == "SCENARIO_10_IMPOSSIBLE_TRAVEL":
                channel = "UPI"
                amount = round(random.uniform(10000.0, 60000.0), 2)
                dist_km = round(random.uniform(1200.0, 2500.0), 2)
                is_new_dev = 1 if random.random() < 0.88 else 0
                is_new_ben = 0
                ben_added_min = random.randint(500, 5000)
                if random.random() < 0.33:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1

            elif scenario == "SCENARIO_11_SHARED_DEVICE_IP":
                channel = "UPI"
                amount = round(random.uniform(15000.0, 50000.0), 2)
                dist_km = round(random.uniform(10.0, 80.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 1 if random.random() < 0.85 else 0
                ben_added_min = random.randint(30, 300)
                if random.random() < 0.33:
                    is_fraud = 0
                    risk_label = "BORDERLINE"
                    is_flagged_alert = 1
                else:
                    is_fraud = 1
                    risk_label = "FRAUDULENT"
                    is_flagged_alert = 1

            else: # SCENARIO_12_MIXED_BORDERLINE_TRAVEL
                channel = random.choice(["UPI", "NEFT"])
                amount = round(random.uniform(15000.0, 80000.0), 2)
                dist_km = round(random.uniform(1500.0, 3500.0), 2)
                is_new_dev = 1 if random.random() < 0.85 else 0
                is_new_ben = 0
                ben_added_min = random.randint(2000, 20000)
                is_fraud = 0
                risk_label = "BORDERLINE"
                is_flagged_alert = 1

            # Final Channel Regulatory Enforcement
            if channel == "RTGS":
                amount = max(amount, 200000.00)
            elif channel == "UPI":
                amount = min(amount, 99999.00)
                amount = max(amount, 10.00)

            # Ensure double entry balance accounting
            bal_before = realtime_balances[sender_acc_id]
            if bal_before < amount:
                realtime_balances[sender_acc_id] += (amount + 50000.0) # Top up balance if needed
                bal_before = realtime_balances[sender_acc_id]
            
            bal_after = round(bal_before - amount, 2)
            realtime_balances[sender_acc_id] = bal_after
            realtime_balances[receiver_acc_id] = round(realtime_balances[receiver_acc_id] + amount, 2)

            # Feature Ratios & Engine Metrics
            hist_avg = acc_map[sender_acc_id]["historical_30d_avg_tx_amt_inr"]
            amt_ratio = round(amount / max(1.0, hist_avg), 4)

            vpa_sender = f"user{sender_acc_id.split('_')[-1]}{random.choice(UPI_HANDLES)}"
            vpa_receiver = f"user{receiver_acc_id.split('_')[-1]}{random.choice(UPI_HANDLES)}"

            # 1. Feature Row (X Matrix)
            f_row = {
                "transaction_id": tx_id,
                "timestamp": tx_timestamp_str,
                "day_of_month": day_offset + 1,
                "hour_of_day": hour,
                "day_of_week": tx_dt.weekday(),
                "channel": channel,
                "transaction_type": "P2P" if channel == "UPI" else ("B2B" if channel == "RTGS" else "C2B"),
                "amount_inr": amount,
                "status": "SUCCESS",
                "sender_account_id": sender_acc_id,
                "receiver_account_id": receiver_acc_id,
                "sender_customer_id": sender_cust_id,
                "receiver_customer_id": receiver_cust_id,
                "sender_vpa": vpa_sender,
                "receiver_vpa": vpa_receiver,
                "sender_ifsc": acc_map[sender_acc_id]["ifsc_code_synthetic"],
                "receiver_ifsc": acc_map[receiver_acc_id]["ifsc_code_synthetic"],
                "device_id": dev_id,
                "ip_address": f"103.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
                "tx_city": sender_cust["home_city"],
                "tx_state": sender_cust["home_state"],
                "tx_lat": round(home_lat + (random.uniform(-0.05, 0.05) if dist_km < 50 else random.uniform(2.0, 10.0)), 4),
                "tx_long": round(home_long + (random.uniform(-0.05, 0.05) if dist_km < 50 else random.uniform(2.0, 10.0)), 4),
                "distance_from_home_km": dist_km,
                "is_new_device": is_new_dev,
                "is_new_beneficiary": is_new_ben,
                "time_since_beneficiary_added_min": ben_added_min,
                "amount_ratio_vs_30d_avg": amt_ratio,
                "tx_frequency_24h": random.randint(1, 14),
                "time_since_last_tx_sec": random.randint(30, 86400),
                "account_balance_before": round(bal_before, 2),
                "account_balance_after": round(bal_after, 2)
            }

            # 2. Target & Ground Truth Row (y Matrix + Metadata)
            alert_id = f"ALT_IND_202608_{tx_counter:06d}" if is_flagged_alert == 1 else ""
            t_row = {
                "transaction_id": tx_id,
                "alert_id": alert_id,
                "is_fraud": is_fraud,
                "risk_label": risk_label,
                "is_flagged_alert": is_flagged_alert,
                "scenario_id": scenario
            }

            # 3. Neo4j Graph Edge Row
            g_row = {
                ":START_ID": sender_acc_id,
                ":END_ID": receiver_acc_id,
                "amount_inr": amount,
                "timestamp": tx_timestamp_str,
                "channel": channel,
                "rapid_forward_delta_sec": random.randint(60, 900) if "LAYERING" in scenario or "STRUCTURING" in scenario else 0,
                "scenario_id": scenario,
                ":TYPE": "TRANSFERRED_TO"
            }

            tx_features.append(f_row)
            tx_targets.append(t_row)
            graph_edges.append(g_row)

            tx_counter += 1

        return tx_features, tx_targets, graph_edges
