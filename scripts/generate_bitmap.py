import pandas as pd
import pandas_market_calendars as mcal
from datetime import date, timedelta
import os

def create_trading_calendar_bitmap(calendar_name, start_date, end_date, output_file):
    """
    Generates a bitmap file for a given market calendar and date range.

    Args:
        calendar_name (str): The name of the market calendar (e.g., 'SSE').
        start_date (date): The start date of the range.
        end_date (date): The end date of the range.
        output_file (str): The path to the output bitmap file.
    """
    # Get the market calendar
    calendar = mcal.get_calendar(calendar_name)

    # Get all trading days in the full range
    trading_days = calendar.valid_days(start_date=start_date, end_date=end_date)
    trading_days_set = set(dt.date() for dt in trading_days)

    # Correct for 1990 SSE history
    if calendar_name == 'SSE' and start_date.year <= 1990:
        sse_start_date = date(1990, 12, 19)
        # Remove all 1990 dates before the official start
        trading_days_set = {d for d in trading_days_set if d >= sse_start_date or d.year != 1990}

    # Calculate the total number of days in the range
    total_days = (end_date - start_date).days + 1
    # Create a byte array for the bitmap, one bit per day
    bitmap = bytearray((total_days + 7) // 8)

    # Iterate through each day and set the corresponding bit if it's a trading day
    for i in range(total_days):
        current_date = start_date + timedelta(days=i)
        if current_date in trading_days_set:
            byte_index = i // 8
            bit_index = 7 - (i % 8)  # Big-endian bit order
            bitmap[byte_index] |= (1 << bit_index)

    # Write the bitmap to the output file
    with open(output_file, 'wb') as f:
        # Write the start date as a header (YYYYMMDD)
        f.write(start_date.strftime('%Y%m%d').encode('ascii'))
        # Write the bitmap data
        f.write(bitmap)

    print(f"Successfully generated bitmap for {calendar_name} from {start_date} to {end_date}.")
    print(f"Bitmap saved to: {output_file}")

if __name__ == "__main__":
    # Configuration
    CALENDAR_NAME = 'SSE'  # Shanghai Stock Exchange
    START_DATE = date(1990, 1, 1)
    END_DATE = date(2049, 12, 31)

    # Output file will be in the same directory as the script
    output_dir = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_FILE = os.path.join(output_dir, f"{CALENDAR_NAME.lower()}_calendar.bin")

    create_trading_calendar_bitmap(CALENDAR_NAME, START_DATE, END_DATE, OUTPUT_FILE)
