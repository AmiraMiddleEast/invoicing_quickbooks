#!/usr/bin/env python3
"""
Amira Invoicing Manager
=======================
Connects SeaTable data with QuickBooks for automated invoice generation.

For Railway deployment:
- Set environment variables in Railway dashboard
- Or use defaults for development
"""

import os
import json
import base64
import requests
from datetime import datetime, timedelta
from flask import Flask, request, redirect, jsonify, send_from_directory
from flask_cors import CORS
from urllib.parse import urlencode

app = Flask(__name__, static_folder='.')
CORS(app)

# =============================================================================
# CONFIGURATION (uses environment variables for Railway)
# =============================================================================

CONFIG = {
    # QuickBooks OAuth
    'client_id': os.environ.get('QB_CLIENT_ID', 'ABxnnDm9mUtNpTo4LoopepmvUmAvboF34607dGQSDWHtVUT1gA'),
    'client_secret': os.environ.get('QB_CLIENT_SECRET', 'CcxIlIpUVnjJPuGIkwI2LB6sjS7q1IzyNxL6ewuj'),
    'redirect_uri': os.environ.get('QB_REDIRECT_URI', 'http://localhost:8080/callback'),
    'environment': os.environ.get('QB_ENVIRONMENT', 'sandbox'),  # 'sandbox' or 'production'
    
    # QuickBooks API URLs
    'auth_url': 'https://appcenter.intuit.com/connect/oauth2',
    'token_url': 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
    'sandbox_api': 'https://sandbox-quickbooks.api.intuit.com',
    'production_api': 'https://quickbooks.api.intuit.com',
    
    # Company ID (Realm ID)
    'sandbox_realm_id': os.environ.get('QB_SANDBOX_REALM_ID', '9341455864327428'),
    'production_realm_id': os.environ.get('QB_PRODUCTION_REALM_ID', ''),
    
    # SeaTable
    'seatable_url': 'https://cloud.seatable.io',
    'seatable_token': '',  # Will be set from frontend
    'seatable_dtable_uuid': '78178a41-81a5-440c-936a-ebb75tried96',
    
    # Free Minutes per Package
    'free_minutes': {
        'Start': 250,
        'Core': 350,
        'Pro': 500,
        'Enterprise': 1000
    }
}

# Token storage (in production, use secure storage!)
tokens = {
    'access_token': None,
    'refresh_token': None,
    'expires_at': None,
    'realm_id': None
}

# =============================================================================
# QUICKBOOKS OAUTH
# =============================================================================

@app.route('/auth/quickbooks')
def auth_quickbooks():
    """Initiate QuickBooks OAuth flow"""
    params = {
        'client_id': CONFIG['client_id'],
        'response_type': 'code',
        'scope': 'com.intuit.quickbooks.accounting',
        'redirect_uri': CONFIG['redirect_uri'],
        'state': 'amira_invoicing'
    }
    auth_url = f"{CONFIG['auth_url']}?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback')
def oauth_callback():
    """Handle OAuth callback from QuickBooks"""
    code = request.args.get('code')
    realm_id = request.args.get('realmId')
    error = request.args.get('error')
    
    if error:
        return f"""
        <html><body>
        <h1>Authorization Failed</h1>
        <p>Error: {error}</p>
        <p><a href="/">Return to app</a></p>
        </body></html>
        """
    
    if code:
        # Exchange code for tokens
        token_response = exchange_code_for_tokens(code)
        if token_response:
            tokens['access_token'] = token_response.get('access_token')
            tokens['refresh_token'] = token_response.get('refresh_token')
            tokens['expires_at'] = datetime.now() + timedelta(seconds=token_response.get('expires_in', 3600))
            tokens['realm_id'] = realm_id or CONFIG['sandbox_realm_id']
            
            return """
            <html>
            <head><meta http-equiv="refresh" content="2;url=/"></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1 style="color: #10B981;">✓ Connected to QuickBooks!</h1>
            <p>Redirecting back to the app...</p>
            </body>
            </html>
            """
    
    return "Authorization failed. Please try again."

def exchange_code_for_tokens(code):
    """Exchange authorization code for access/refresh tokens"""
    auth_header = base64.b64encode(
        f"{CONFIG['client_id']}:{CONFIG['client_secret']}".encode()
    ).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': CONFIG['redirect_uri']
    }
    
    response = requests.post(CONFIG['token_url'], headers=headers, data=data)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Token exchange failed: {response.text}")
        return None

def refresh_access_token():
    """Refresh the access token using refresh token"""
    if not tokens['refresh_token']:
        return False
    
    auth_header = base64.b64encode(
        f"{CONFIG['client_id']}:{CONFIG['client_secret']}".encode()
    ).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': tokens['refresh_token']
    }
    
    response = requests.post(CONFIG['token_url'], headers=headers, data=data)
    if response.status_code == 200:
        token_data = response.json()
        tokens['access_token'] = token_data.get('access_token')
        tokens['refresh_token'] = token_data.get('refresh_token')
        tokens['expires_at'] = datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))
        return True
    return False

def get_qb_headers():
    """Get headers for QuickBooks API calls"""
    # Check if token needs refresh
    if tokens['expires_at'] and datetime.now() >= tokens['expires_at']:
        refresh_access_token()
    
    return {
        'Authorization': f"Bearer {tokens['access_token']}",
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

def get_api_base():
    """Get the appropriate API base URL"""
    if CONFIG['environment'] == 'production':
        return CONFIG['production_api']
    return CONFIG['sandbox_api']

def get_realm_id():
    """Get the appropriate realm ID"""
    return tokens['realm_id'] or CONFIG['sandbox_realm_id']

# =============================================================================
# QUICKBOOKS API ENDPOINTS
# =============================================================================

@app.route('/api/qb/status')
def qb_status():
    """Check QuickBooks connection status"""
    connected = tokens['access_token'] is not None
    return jsonify({
        'connected': connected,
        'environment': CONFIG['environment'],
        'realm_id': get_realm_id() if connected else None,
        'expires_at': tokens['expires_at'].isoformat() if tokens['expires_at'] else None
    })

@app.route('/api/qb/company')
def qb_company_info():
    """Get QuickBooks company info"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/companyinfo/{get_realm_id()}"
    response = requests.get(url, headers=get_qb_headers())
    
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/customers')
def qb_get_customers():
    """Get all customers from QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/query"
    query = "SELECT * FROM Customer MAXRESULTS 1000"
    
    response = requests.get(
        url, 
        headers=get_qb_headers(),
        params={'query': query}
    )
    
    if response.status_code == 200:
        data = response.json()
        customers = data.get('QueryResponse', {}).get('Customer', [])
        return jsonify({'customers': customers})
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/customer', methods=['POST'])
def qb_create_customer():
    """Create a new customer in QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    customer_data = request.json
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/customer"
    
    response = requests.post(url, headers=get_qb_headers(), json=customer_data)
    
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/invoice', methods=['POST'])
def qb_create_invoice():
    """Create a new invoice in QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    invoice_data = request.json
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/invoice"
    
    response = requests.post(url, headers=get_qb_headers(), json=invoice_data)
    
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/invoices')
def qb_get_invoices():
    """Get recent invoices from QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/query"
    query = "SELECT * FROM Invoice ORDERBY TxnDate DESC MAXRESULTS 100"
    
    response = requests.get(
        url, 
        headers=get_qb_headers(),
        params={'query': query}
    )
    
    if response.status_code == 200:
        data = response.json()
        invoices = data.get('QueryResponse', {}).get('Invoice', [])
        return jsonify({'invoices': invoices})
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/items')
def qb_get_items():
    """Get all items/services from QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/query"
    query = "SELECT * FROM Item WHERE Type = 'Service' MAXRESULTS 100"
    
    response = requests.get(
        url, 
        headers=get_qb_headers(),
        params={'query': query}
    )
    
    if response.status_code == 200:
        data = response.json()
        items = data.get('QueryResponse', {}).get('Item', [])
        return jsonify({'items': items})
    return jsonify({'error': response.text}), response.status_code

@app.route('/api/qb/item', methods=['POST'])
def qb_create_item():
    """Create a new service item in QuickBooks"""
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    item_data = request.json
    url = f"{get_api_base()}/v3/company/{get_realm_id()}/item"
    
    response = requests.post(url, headers=get_qb_headers(), json=item_data)
    
    if response.status_code == 200:
        return jsonify(response.json())
    return jsonify({'error': response.text}), response.status_code

# =============================================================================
# SEATABLE API ENDPOINTS  
# =============================================================================

@app.route('/api/seatable/data')
def get_seatable_data():
    """Get partners and companies from SeaTable"""
    if not CONFIG['seatable_token']:
        return jsonify({'error': 'SeaTable not configured'}), 400
    
    try:
        # Get access token - this also returns the dtable_uuid!
        token_url = f"{CONFIG['seatable_url']}/api/v2.1/dtable/app-access-token/"
        token_response = requests.get(
            token_url,
            headers={'Authorization': f"Bearer {CONFIG['seatable_token']}"}
        )
        
        if token_response.status_code != 200:
            return jsonify({'error': f'Failed to get SeaTable access token: {token_response.text}'}), 400
        
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        dtable_uuid = token_data.get('dtable_uuid')  # UUID comes from API!
        
        if not dtable_uuid:
            return jsonify({'error': 'Could not get dtable_uuid from SeaTable'}), 400
        
        # Get Partners
        partners_url = f"{CONFIG['seatable_url']}/api-gateway/api/v2/dtables/{dtable_uuid}/rows/?table_name=Partners"
        partners_response = requests.get(
            partners_url,
            headers={'Authorization': f"Bearer {access_token}"}
        )
        partners = []
        if partners_response.status_code == 200:
            for row in partners_response.json().get('rows', []):
                partners.append({
                    'id': row.get('_id'),
                    'name': row.get('Doq7') or row.get('name') or row.get('Name', ''),
                    'email': row.get('s9S4') or row.get('email') or '',
                    'is_direct': row.get('eidm') or row.get('is_direct') or False
                })
        
        # Get Companies
        companies_url = f"{CONFIG['seatable_url']}/api-gateway/api/v2/dtables/{dtable_uuid}/rows/?table_name=Companies"
        companies_response = requests.get(
            companies_url,
            headers={'Authorization': f"Bearer {access_token}"}
        )
        companies = []
        if companies_response.status_code == 200:
            for row in companies_response.json().get('rows', []):
                companies.append({
                    'id': row.get('_id'),
                    'name': row.get('ma2n') or row.get('company_name') or row.get('Company', ''),
                    'partner_id': row.get('0000') or row.get('partner_id') or '',
                    'package': row.get('package') or row.get('Package') or 'Start',
                    'monthly_fee': float(row.get('monthly_fee') or row.get('Monthly_Fee') or 0),
                    'whatsapp_fee': float(row.get('whatsapp_fee') or 0),
                    'email_fee': float(row.get('email_fee') or 0),
                    'lines_fee': float(row.get('lines_fee') or 0),
                    'numbers_fee': float(row.get('numbers_fee') or 0),
                    'start_date': row.get('H7aK') or row.get('start_date') or '',
                    'end_date': row.get('0It0') or row.get('end_date') or ''
                })
        
        return jsonify({
            'partners': partners,
            'companies': companies,
            'dtable_uuid': dtable_uuid
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# =============================================================================
# INVOICE GENERATION LOGIC
# =============================================================================

@app.route('/api/generate-invoices', methods=['POST'])
def generate_invoices():
    """
    Generate invoices based on SeaTable data and usage data.
    
    Request body:
    {
        "month": "2024-12",
        "usage_data": [
            {
                "partner_name": "Virella AI",
                "customer_name": "Customer A",
                "minutes_used": 500,
                "whatsapp_messages": 100,
                "email_messages": 50
            }
        ]
    }
    """
    if not tokens['access_token']:
        return jsonify({'error': 'Not connected to QuickBooks'}), 401
    
    data = request.json
    month = data.get('month')
    usage_data = data.get('usage_data', [])
    
    # Get SeaTable data
    seatable_response = get_seatable_data()
    if seatable_response[1] if isinstance(seatable_response, tuple) else 200 != 200:
        return jsonify({'error': 'Failed to get SeaTable data'}), 500
    
    seatable_data = seatable_response.get_json()
    partners = {p['name']: p for p in seatable_data['partners']}
    companies = seatable_data['companies']
    
    # Group companies by partner
    companies_by_partner = {}
    for company in companies:
        partner_id = company['partner_id']
        # Find partner name from ID
        partner_name = None
        for p in seatable_data['partners']:
            if p['id'] == partner_id or p['name'] == partner_id:
                partner_name = p['name']
                break
        
        if partner_name:
            if partner_name not in companies_by_partner:
                companies_by_partner[partner_name] = []
            companies_by_partner[partner_name].append(company)
    
    generated_invoices = []
    
    # Process each partner
    for partner_name, partner_companies in companies_by_partner.items():
        partner = partners.get(partner_name, {})
        is_direct = partner.get('is_direct', False)
        
        if is_direct:
            # Direct customers: One invoice per customer
            for company in partner_companies:
                invoice = create_direct_customer_invoice(
                    partner_name=partner_name,
                    company=company,
                    usage_data=usage_data,
                    month=month
                )
                if invoice:
                    generated_invoices.append(invoice)
        else:
            # WL Partner: One invoice for all customers
            invoice = create_wl_partner_invoice(
                partner_name=partner_name,
                companies=partner_companies,
                usage_data=usage_data,
                month=month
            )
            if invoice:
                generated_invoices.append(invoice)
    
    return jsonify({
        'success': True,
        'invoices_generated': len(generated_invoices),
        'invoices': generated_invoices
    })

def create_direct_customer_invoice(partner_name, company, usage_data, month):
    """Create invoice for a direct customer"""
    customer_name = company['name']
    unique_id = f"{partner_name} | {customer_name}"
    
    # Find usage for this customer
    customer_usage = None
    for usage in usage_data:
        if usage.get('partner_name') == partner_name and usage.get('customer_name') == customer_name:
            customer_usage = usage
            break
    
    # Calculate line items
    line_items = []
    total = 0
    
    # Monthly fees
    if company['monthly_fee'] > 0:
        line_items.append({
            'Description': f"Monthly Package - {company.get('package', 'Standard')}",
            'Amount': company['monthly_fee'],
            'DetailType': 'SalesItemLineDetail'
        })
        total += company['monthly_fee']
    
    for fee_type in ['whatsapp_fee', 'email_fee', 'lines_fee', 'numbers_fee']:
        if company.get(fee_type, 0) > 0:
            line_items.append({
                'Description': fee_type.replace('_', ' ').title(),
                'Amount': company[fee_type],
                'DetailType': 'SalesItemLineDetail'
            })
            total += company[fee_type]
    
    # Usage charges (with free minutes deduction for direct customers)
    if customer_usage:
        package = company.get('package', 'Start')
        free_mins = CONFIG['free_minutes'].get(package, 0)
        minutes_used = customer_usage.get('minutes_used', 0)
        billable_minutes = max(0, minutes_used - free_mins)
        
        if billable_minutes > 0:
            minute_rate = 0.12  # AED per minute
            minute_charge = billable_minutes * minute_rate
            line_items.append({
                'Description': f"Voice Minutes: {minutes_used} used - {free_mins} free = {billable_minutes} billable @ 0.12 AED",
                'Amount': minute_charge,
                'DetailType': 'SalesItemLineDetail'
            })
            total += minute_charge
        
        # WhatsApp messages
        wa_messages = customer_usage.get('whatsapp_messages', 0)
        if wa_messages > 0:
            wa_charge = wa_messages * 0.15
            line_items.append({
                'Description': f"WhatsApp Messages: {wa_messages} @ 0.15 AED",
                'Amount': wa_charge,
                'DetailType': 'SalesItemLineDetail'
            })
            total += wa_charge
        
        # Email messages
        email_messages = customer_usage.get('email_messages', 0)
        if email_messages > 0:
            email_charge = email_messages * 0.05
            line_items.append({
                'Description': f"Email Messages: {email_messages} @ 0.05 AED",
                'Amount': email_charge,
                'DetailType': 'SalesItemLineDetail'
            })
            total += email_charge
    
    return {
        'type': 'direct',
        'customer_id': unique_id,
        'customer_name': customer_name,
        'partner_name': partner_name,
        'month': month,
        'line_items': line_items,
        'total': total
    }

def create_wl_partner_invoice(partner_name, companies, usage_data, month):
    """Create invoice for a WL partner (all their customers combined)"""
    line_items = []
    total = 0
    
    # Calculate total free minutes pool
    total_free_minutes = 0
    for company in companies:
        package = company.get('package', 'Start')
        total_free_minutes += CONFIG['free_minutes'].get(package, 0)
    
    # Monthly fees for all customers
    for company in companies:
        customer_name = company['name']
        
        if company['monthly_fee'] > 0:
            line_items.append({
                'Description': f"{customer_name} - Monthly Package ({company.get('package', 'Standard')})",
                'Amount': company['monthly_fee'],
                'DetailType': 'SalesItemLineDetail'
            })
            total += company['monthly_fee']
        
        for fee_type, label in [('whatsapp_fee', 'WhatsApp'), ('email_fee', 'Email'), 
                                 ('lines_fee', 'Lines'), ('numbers_fee', 'Numbers')]:
            if company.get(fee_type, 0) > 0:
                line_items.append({
                    'Description': f"{customer_name} - {label} Addon",
                    'Amount': company[fee_type],
                    'DetailType': 'SalesItemLineDetail'
                })
                total += company[fee_type]
    
    # Aggregate usage for all customers under this partner
    total_minutes = 0
    total_wa_messages = 0
    total_email_messages = 0
    
    for usage in usage_data:
        if usage.get('partner_name') == partner_name:
            total_minutes += usage.get('minutes_used', 0)
            total_wa_messages += usage.get('whatsapp_messages', 0)
            total_email_messages += usage.get('email_messages', 0)
    
    # Calculate billable minutes (after free minutes pool deduction)
    billable_minutes = max(0, total_minutes - total_free_minutes)
    
    if total_minutes > 0:
        if billable_minutes > 0:
            minute_rate = 0.12  # AED per minute
            minute_charge = billable_minutes * minute_rate
            line_items.append({
                'Description': f"Voice Minutes: {total_minutes} used - {total_free_minutes} free pool = {billable_minutes} billable @ 0.12 AED",
                'Amount': minute_charge,
                'DetailType': 'SalesItemLineDetail'
            })
            total += minute_charge
        else:
            line_items.append({
                'Description': f"Voice Minutes: {total_minutes} used (within {total_free_minutes} free pool)",
                'Amount': 0,
                'DetailType': 'SalesItemLineDetail'
            })
    
    if total_wa_messages > 0:
        wa_charge = total_wa_messages * 0.15
        line_items.append({
            'Description': f"WhatsApp Messages (all customers): {total_wa_messages} @ 0.15 AED",
            'Amount': wa_charge,
            'DetailType': 'SalesItemLineDetail'
        })
        total += wa_charge
    
    if total_email_messages > 0:
        email_charge = total_email_messages * 0.05
        line_items.append({
            'Description': f"Email Messages (all customers): {total_email_messages} @ 0.05 AED",
            'Amount': email_charge,
            'DetailType': 'SalesItemLineDetail'
        })
        total += email_charge
    
    return {
        'type': 'wl_partner',
        'customer_id': partner_name,
        'customer_name': partner_name,
        'partner_name': partner_name,
        'month': month,
        'line_items': line_items,
        'total': total,
        'customer_count': len(companies),
        'free_minutes_pool': total_free_minutes
    }

# =============================================================================
# SERVE FRONTEND
# =============================================================================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    print("\n" + "="*60)
    print("  AMIRA INVOICING MANAGER")
    print("="*60)
    print(f"\n  Server running at: http://localhost:{port}")
    print(f"  Environment: {CONFIG['environment'].upper()}")
    print(f"\n  1. Open http://localhost:{port} in your browser")
    print(f"  2. Click 'Connect to QuickBooks' to authorize")
    print(f"  3. Configure SeaTable connection")
    print(f"  4. Generate invoices!")
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
