# Amira Invoicing Manager

Automated invoice generation connecting SeaTable (customer data) with QuickBooks Online.

## Features

- 🔗 **QuickBooks Integration**: OAuth2 connection to create invoices
- 📊 **SeaTable Sync**: Pulls partners and customers from your database
- 📈 **Usage Tracking**: Import or manually enter consumption data
- 📄 **Smart Invoicing**:
  - **Direct Customers**: One invoice per customer (with individual free minutes)
  - **WL Partners**: One invoice per partner (pooled free minutes across all their customers)
- 💰 **Automatic Calculations**: Monthly fees + usage charges - free minutes

## Setup

### 1. Install Dependencies

```bash
cd invoicing_manager
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python app.py
```

### 3. Open the App

Go to: **http://localhost:8080**

## Configuration

### QuickBooks (Already configured)

- Environment: Sandbox
- Client ID: `ABxnnDm9mUtNpTo4LoopepmvUmAvboF34607dGQSDWHtVUT1gA`
- Realm ID: `9341455864327428`

### SeaTable

Enter your API token in the Connections page.

## Invoice Logic

### Direct Customers (is_direct = true)
- One invoice per customer
- Free minutes deducted per customer based on their package
- Unique ID: `Partner Name | Customer Name`

### WL Partners (is_direct = false)
- One invoice per partner containing all their customers
- Free minutes pooled across all customers
  - Example: 2x Core (700 min) + 2x Start (500 min) = 1,200 free min
- Usage aggregated at partner level

### Free Minutes by Package
| Package | Free Minutes |
|---------|--------------|
| Start | 250 |
| Core | 350 |
| Pro | 500 |
| Enterprise | 1,000 |

### Rates
| Item | Rate |
|------|------|
| Voice Minutes | 0.12 AED/min |
| WhatsApp | 0.15 AED/msg |
| Email | 0.05 AED/msg |

## File Structure

```
invoicing_manager/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── static/
│   └── index.html      # Frontend UI
└── README.md
```

## Switching to Production

1. Edit `app.py`:
   - Change `environment` to `'production'`
   - Set `production_realm_id` to your real QuickBooks company ID

2. Submit app for Intuit review (required for production OAuth)

3. After approval, use production credentials

## Security Notes

⚠️ The client secret in `app.py` should be rotated after development.

For production:
- Store credentials in environment variables
- Use a proper secrets manager
- Enable HTTPS
