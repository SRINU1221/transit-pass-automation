# ============================================================
#  config.py — Transit Pass Automation — Telangana EPermit
# ============================================================

# --- URLs ---
BASE_URL  = "https://mines.telangana.gov.in"
LOGIN_URL = f"{BASE_URL}/EPermit/Login.aspx"

# --- Login Page Selectors (confirmed) ---
SEL_USERNAME  = "#txtLoginUsername"
SEL_PASSWORD  = "#txtLoginPassword"
SEL_LOGIN_BTN = "#btnGetOtp"   # "LOGIN" button → triggers OTP

# --- OTP Input Selectors ---
OTP_INPUT_SELECTORS = [
    "input[id$='txtOTP']",
    "input[id$='txtOtp']",
    "input[id$='OTP']",
    "input[id$='Otp']",
    "#txtOTP",
    "#txtOtp",
    "#ctl00_ContentPlaceHolder1_txtOTP",
    "#ctl00_ContentPlaceHolder1_txtOtp",
    "input[id*='OTP']:not([type='submit']):not([type='button']):not([id*='btn'])",
    "input[id*='Otp']:not([type='submit']):not([type='button']):not([id*='btn'])",
    "input[placeholder*='OTP']",
    "input[placeholder*='Enter OTP']",
]

# --- OTP Submit — same #btnGetOtp button is reused for OTP verification ---
OTP_SUBMIT_SELECTORS = [
    "#btnGetOtp",
    "input[value='LOGIN']",
    "input[value='Login']",
    "#btnVerifyOTP",
    "input[value='Verify']",
    "button:has-text('LOGIN')",
    "button:has-text('Verify')",
]

# ─────────────────────────────────────────────────────────────
#  Navigation: e-Trans → Permits → Approved Permits
# ─────────────────────────────────────────────────────────────
NAV_ETRANS_MENU = [
    "a:has-text('e-Trans')",      # exact text from screenshot nav bar
    "a:has-text('e-Tran')",
    "a:has-text('E-Trans')",
    "a:has-text('ETrans')",
    "a[href*='ETrans']",
    "a[href*='eTrans']",
    "#lnkETransmit",
    "#lnkETrans",
]
NAV_PERMITS_SUBMENU = [
    "a:has-text('Permits')",
    "a[href*='Permit']",
    "li:has-text('Permits') > a",
]
NAV_APPROVED_PERMITS = [
    "a:has-text('Approved Permits')",
    "a:has-text('Approved')",
    "a[href*='ApprovedPermit']",
    "a[href*='Approved']",
]

# "Click..!" button under the "New" column in the Approved Permits table
TP_NEW_BTN = [
    "table tr td:nth-child(14) a",
    "a[id*='lnkNew']",
    "a[href*='lnkNew']",
    "a:has-text('Click..!')",
    "a:has-text('Click!')",
    "a:has-text('Click')",
    "input[value*='Click']",
    "button:has-text('Click')",
    "input[value='Click..!']",
    "input[value='Click!']",
]

# ─────────────────────────────────────────────────────────────
#  Step 1 — MDL Selection
# ─────────────────────────────────────────────────────────────
# "Type of MDL" dropdown — the FIRST dropdown on the Transit Pass form.
# Selecting "MDL" triggers AJAX / ASP.NET UpdatePanel to render the MDL
# ID dropdown + GET DETAILS button dynamically below it.
MDL_TYPE_DDL = [
    # id contains — short IDs
    "select[id*='ddlMDLType']",
    "select[id*='MDLType']",
    "select[id*='TypeMDL']",
    "select[id*='ddlType']",
    "select[id*='ddlConsigneeType']",
    "select[id*='ConsigneeType']",
    # id ends-with — ASP.NET ContentPlaceHolder-generated long IDs
    "select[id$='ddlMDLType']",
    "select[id$='ddlType']",
    "select[id$='ddlMdlType']",
    "select[id$='TypeofMDL']",
    "select[id$='TypeOfMDL']",
    "select[id$='MDLType']",
    # name-based fallbacks
    "select[name*='ddlMDLType']",
    "select[name*='MDLType']",
    "select[name*='ddlType']",
]
MDL_TYPE_VALUE     = "MDL"        # option text/value when choosing MDL
MDL_TYPE_CONSIGNEE = "Consignee"  # option text/value for Consignee branch

# "MDL ID" dropdown — appears DYNAMICALLY after selecting MDL type.
# CONFIRMED real ID from live portal log:
#   ContentPlaceHolder1_ddl_MDLMTP_AllMDLs  (name=ddl_MDLMTP_AllMDLs)
MDL_ID_DDL = [
    # ✅ CONFIRMED selectors from live portal (highest priority — listed first)
    "select[id*='AllMDLs']",
    "select[id$='AllMDLs']",
    "select[name*='AllMDLs']",
    "select[id*='MDLMTP_AllMDLs']",
    "select[name*='MDLMTP_AllMDLs']",
    # Generic fallbacks
    "select[id*='ddlMDLID']",
    "select[id*='MDLID']",
    "select[id*='ddlMDL']",
    "select[id*='MineID']",
    "select[id*='ddlMDLId']",
    "select[id*='MDLId']",
    "select[id*='ddlMine']",
    # ASP.NET generated id ends-with
    "select[id$='ddlMDLID']",
    "select[id$='ddlMDLId']",
    "select[id$='ddlMDL']",
    "select[id$='MDLID']",
    "select[id$='MineID']",
    # name-based fallbacks
    "select[name*='ddlMDLID']",
    "select[name*='MDLID']",
    "select[name*='ddlMDL']",
]
# MDL ID value is set to the logged-in username at runtime

MDL_GET_DETAILS_BTN = [
    # ✅ CONFIRMED from screenshot: button text is "GET DETAIL" (no S)
    "input[value='GET DETAIL']",
    "input[value='Get Detail']",
    "button:has-text('GET DETAIL')",
    "a:has-text('GET DETAIL')",
    # Also try with S (fallback)
    "input[value='GET DETAILS']",
    "input[value='Get Details']",
    "input[value='GetDetails']",
    "input[value='GET Details']",
    "button:has-text('GET DETAILS')",
    "button:has-text('Get Details')",
    "a:has-text('GET DETAILS')",
    "a:has-text('Get Details')",
    # ID-based selectors
    "#btnGetDetails",
    "#btnGetDetail",
    "input[id*='GetDetails']",
    "input[id*='GetDetail']",
    "input[id*='btnGet']",
    "input[id$='btnGetDetails']",
    "input[id$='btnGetDetail']",
    "input[id$='btnGet']",
    # name-based
    "input[name*='GetDetails']",
    "input[name*='GetDetail']",
    "input[name*='btnGet']",
]

# ─────────────────────────────────────────────────────────────
#  Step 2 — PERMIT INFO / Aggregator
#  Real portal naming follows MDLMTP_ prefix pattern.
#  The debug log in step2 will print the confirmed real ID.
# ─────────────────────────────────────────────────────────────
AGGREGATOR_DDL = [
    # MDLMTP prefix pattern (same as MDL dropdowns — portal convention)
    "select[id*='MDLMTP_Aggreg']",
    "select[id*='ddl_MDLMTP_Aggreg']",
    "select[name*='MDLMTP_Aggreg']",
    "select[id*='Aggregators']",
    "select[id$='Aggregators']",
    "select[name*='Aggregators']",
    # Generic patterns
    "select[id*='Aggregator']",
    "select[id*='ddlAggregator']",
    "select[id*='Aggregat']",
    "select[id*='Lessee']",
    "select[id*='ddlLessee']",
    "select[name*='Aggregator']",
    "select[name*='Lessee']",
]

# ─────────────────────────────────────────────────────────────
#  Step 3 — CONSIGNEE INFO fields
#  Fill order: Dispatch Quantity → Sale Value → Stationery No
#  ✅ Confirmed IDs from portal log: MDLRMTP prefix (note the R)
# ─────────────────────────────────────────────────────────────
DISPATCH_QTY_INPUT = [
    # ✅ CONFIRMED portal IDs (from automation log)
    "input[id*='MDLRMTP_ActualDisptchQty']",
    "input[id*='MDLRMTP_DispatchQty']",
    "input[id*='MDLRMTP_Dispatch']",
    "input[name*='MDLRMTP_ActualDisptchQty']",
    "input[name*='MDLRMTP_Dispatch']",
    # Placeholder selectors (from screenshot)
    "input[placeholder='Quantity']",
    "input[placeholder*='Quantity']",
    # Generic fallbacks
    "input[id*='MDLMTP_DispatchQty']",
    "input[id*='DispatchQty']",
    "input[id*='DispatchQuantity']",
    "input[id*='Quantity']",
    "input[id*='Qty']",
]
STATIONARY_NO_INPUT = [
    # ✅ CONFIRMED portal ID: ContentPlaceHolder1_txt_MDLRMTP_StationeryNo
    "input[id*='MDLRMTP_StationeryNo']",
    "input[id*='MDLRMTP_StationaryNo']",
    "input[id*='MDLRMTP_Station']",
    "input[name*='MDLRMTP_Station']",
    # Placeholder selectors (from screenshot)
    "input[placeholder='Stationery No']",
    "input[placeholder*='Stationery']",
    "input[placeholder*='Stationary']",
    # Generic fallbacks
    "input[id*='MDLMTP_Stationery']",
    "input[id*='StationeryNo']",
    "input[id*='Stationery']",
    "input[id*='StationaryNo']",
    "input[id*='StNo']",
]
SALES_VALUE_INPUT = [
    # ✅ CONFIRMED portal ID: ContentPlaceHolder1_txt_MDLRMTP_SaleValue
    "input[id*='MDLRMTP_SaleValue']",
    "input[id*='MDLRMTP_SalesValue']",
    "input[id*='MDLRMTP_Sale']",
    "input[name*='MDLRMTP_Sale']",
    # Placeholder selectors (from screenshot)
    "input[placeholder='Sale Value']",
    "input[placeholder*='Sale Value']",
    # Generic fallbacks
    "input[id*='MDLMTP_SaleValue']",
    "input[id*='SaleValue']",
    "input[id*='SalesValue']",
    "input[id*='Sales']",
]
CONSIGNEE_NEXT_BTN = [
    # ✅ CONFIRMED from portal screenshot — button text = "NEXT"
    "input[value='NEXT']",
    "input[value='Next']",
    "button:has-text('NEXT')",
    "button:has-text('Next')",
    "input[id*='MDLRMTP_Next']",
    "input[id*='Next']",
    "button[id*='Next']",
]

# ─────────────────────────────────────────────────────────────
#  Step 4 — Vehicle and Driver Information
#  ✅ Confirmed IDs from portal log: MDLRMTP prefix (note the R)
#     ContentPlaceHolder1_DDL_MDLRMTP_VehicleType
#     ContentPlaceHolder1_txt_MDLRMTP_VehicleNo
#     ContentPlaceHolder1_txt_MDLRMTP_DriverName
#     ContentPlaceHolder1_txt_MDLRMTP_DriverLicenseNo
#     ContentPlaceHolder1_txt_MDLRMTP_DriverMobileNo  (assumed)
# ─────────────────────────────────────────────────────────────
VEHICLE_TYPE_DDL = [
    # ✅ CONFIRMED: ContentPlaceHolder1_DDL_MDLRMTP_VehicleType
    "select[id*='MDLRMTP_VehicleType']",
    "select[id*='MDLRMTP_Vehicle']",
    "select[name*='MDLRMTP_VehicleType']",
    # Generic fallbacks
    "select[id*='MDLMTP_VehicleType']",
    "select[id*='VehicleType']",
    "select[id*='ddlVehicleType']",
    "select[id*='VehType']",
]
VEHICLE_TYPE_VALUE = "Tipper"

VEHICLE_NO_INPUT = [
    # ✅ CONFIRMED: ContentPlaceHolder1_txt_MDLRMTP_VehicleNo
    "input[id*='MDLRMTP_VehicleNo']",
    "input[name*='MDLRMTP_VehicleNo']",
    # Generic fallbacks
    "input[id*='MDLMTP_VehicleNo']",
    "input[id*='VehicleNo']",
    "input[id*='VehicleNumber']",
]
DRIVER_NAME_INPUT = [
    # ✅ CONFIRMED: ContentPlaceHolder1_txt_MDLRMTP_DriverName
    "input[id*='MDLRMTP_DriverName']",
    "input[name*='MDLRMTP_DriverName']",
    # Generic fallbacks
    "input[id*='MDLMTP_DriverName']",
    "input[id*='DriverName']",
    "input[id*='Driver']",
]
DRIVER_LICENSE_INPUT = [
    # ✅ CONFIRMED: ContentPlaceHolder1_txt_MDLRMTP_DriverLicenseNo
    "input[id*='MDLRMTP_DriverLicenseNo']",
    "input[id*='MDLRMTP_DriverLicense']",
    "input[id*='MDLRMTP_License']",
    "input[name*='MDLRMTP_DriverLicense']",
    # Generic fallbacks
    "input[id*='MDLMTP_DriverLicense']",
    "input[id*='DriverLicenseNo']",
    "input[id*='LicenseNo']",
    "input[id*='License']",
    "input[id*='DLNo']",
]
DRIVER_MOBILE_INPUT = [
    # ✅ Likely ID: ContentPlaceHolder1_txt_MDLRMTP_DriverMobileNo
    "input[id*='MDLRMTP_DriverMobileNo']",
    "input[id*='MDLRMTP_DriverMobile']",
    "input[id*='MDLRMTP_Mobile']",
    "input[id*='MDLRMTP_Phone']",
    "input[name*='MDLRMTP_DriverMobile']",
    "input[name*='MDLRMTP_Mobile']",
    # Placeholder fallback
    "input[placeholder='Driver Mobile']",
    "input[placeholder*='Mobile']",
    "input[placeholder*='Phone']",
    # Generic fallbacks
    "input[id*='MDLMTP_Mobile']",
    "input[id*='DriverMobile']",
    "input[id*='MobileNo']",
    "input[id*='Mobile']",
    "input[id*='Phone']",
    "input[id*='ContactNo']",
]
PRINT_TP_BTN = [
    "input[value='Print Transit Pass']",
    "input[value*='Print Transit']",
    "input[value='PRINT TRANSIT PASS']",
    "button:has-text('Print Transit Pass')",
    "button:has-text('Print')",
    "input[id*='MDLRMTP_Print']",
    "input[id*='MDLRMTP_PrintTP']",
    "#btnPrintTP",
    "#btnPrint",
    "input[id*='PrintTP']",
    "input[id*='Print']",
]

# ─────────────────────────────────────────────────────────────
#  Transit Pass Popup — in-page PRINT button
#  This is the "PRINT" button on the transit pass popup page,
#  located below the MDL signature and above the printer
#  guidelines section.  Clicking it triggers window.print()
#  (we suppress that and use CDP instead).
# ─────────────────────────────────────────────────────────────
POPUP_PRINT_BTN = [
    "input[value='PRINT']",
    "input[value='Print']",
    "button:has-text('PRINT')",
    "button:has-text('Print')",
    "input[type='button'][value*='PRINT']",
    "input[type='submit'][value*='PRINT']",
    "input[id*='btnPrint']",
    "input[id*='Print']",
    "button[id*='Print']",
    "a:has-text('PRINT')",
    "a:has-text('Print')",
]


# ─────────────────────────────────────────────────────────────
#  Step 1b — TP (Transit Pass) — TYPE OF CONSIGNEE form
#  From screenshot: one row with 2 dropdowns + GET DETAIL button
#    [Type of Consignee: MDL ▼]  [MDL: Select ▼]  [GET DETAIL]
#  First dropdown = Type of Consignee (select MDL here)
#  Second dropdown = Dynamic MDL list (select by MDL ID)
# ─────────────────────────────────────────────────────────────
TP_CONSIGNEE_TYPE_DDL = [
    # Most specific first
    "select[id*='ddlConsigneeType']",
    "select[id*='ConsigneeType']",
    "select[id*='ddlMDLType']",
    "select[id*='MDLType']",
    "select[id*='TypeMDL']",
    "select[id*='ddlType']",
    # Generic first SELECT on the page (Type of Consignee is always first)
    "select:first-of-type",
]

# Dynamic MDL dropdown — appears AFTER selecting MDL in Type of Consignee
# This is the SECOND dropdown on the same row, labeled 'MDL'
# Options look like: "M222099154 - P Veera Reddy"
TP_DYNAMIC_DDL = [
    # Most common portal ID patterns for this second MDL dropdown
    "select[id*='AllMDLs']",
    "select[id*='ddlMDL']:not([id*='Type']):not([id*='Consignee'])",
    "select[id*='MDLID']",
    "select[id*='ConsigneeID']",
    "select[id*='ddlConsignee']:not([id*='Type'])",
    "select[id*='AllConsignees']",
    # Row/container based
    "div[id*='Consignee'] select",
    "span[id*='Consignee'] select",
    "tr[id*='Consignee'] select",
    # Fallback: second SELECT element on page (first = Type of Consignee)
    "select:nth-of-type(2)",
]

TP_DECIMAL_PLACES_CONTROL = [
    "input[id*='decimal']",
    "input[id*='Decimal']",
    "input[id*='decplace']",
    "input[id*='decplaces']",
    "input[type='checkbox'][id*='Qty']",
    "input[type='checkbox'][id*='Quantity']",
    "span:has-text('0.00')",
    "label:has-text('0.00')",
    "a:has-text('0.00')",
    "span:has-text('0')",
    "label:has-text('0')",
]

TP_CALCULATE_BTN = [
    "input[value='CALCULATE']",
    "input[value='Calculate']",
    "button:has-text('CALCULATE')",
    "button:has-text('Calculate')",
    "input[id*='btnCalculate']",
    "input[id*='Calculate']",
    "input[id*='btnCalc']",
    "input[id*='Calc']",
]

TP_SUBMIT_BTN = [
    "input[value='SUBMIT']",
    "input[value='Submit']",
    "button:has-text('SUBMIT')",
    "button:has-text('Submit')",
    "input[id*='btnSubmit']",
    "input[id*='Submit']",
]



# ─────────────────────────────────────────────────────────────────
#  Automation Settings
# ─────────────────────────────────────────────────────────────────
DELAY_BETWEEN_RECORDS = 3.0
PAGE_LOAD_TIMEOUT     = 30_000
ELEMENT_TIMEOUT       = 10_000
OTP_WAIT_TIMEOUT      = 180
MAX_RETRIES           = 2
HEADLESS              = False

# Default PDF save folder — Desktop/TransitPass_PDFs
# The app UI lets the user override this at run-time.
PDF_FOLDER_LABEL = "Transit Pass PDF Folder"
import os as _os
PDF_SAVE_FOLDER = _os.path.join(
    _os.path.expanduser("~"), "Desktop", "TransitPass_PDFs"
)
