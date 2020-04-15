import simplejson as json
import psycopg2
import traceback
import decimal
from datetime import datetime
import requests


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def lambda_handler(event, context):
    try:

        # connect to the database
        connection = psycopg2.connect(user="pmok3",
                                      password="paydontwait",
                                      host="database117.ci9cgiakdb8y.us-east-2.rds.amazonaws.com",
                                      port="5432",
                                      database="paydontwaitdatabase")

        cursor = connection.cursor()

        # Getting the ticket number and table_id from frontend
        data = json.loads(event["body"])

        print(data)

        ticket = data["ticket"]
        table_id = data["table_id"]

        # Make preload object to get receipt
        receipt = json.dumps({"store_id": "monca04308",
                              "api_token": "y6Hx5c2KyAIqkDlPeepY",
                              "checkout_id": "chkt2E24504308",
                              "ticket": ticket,
                              "environment": "qa",
                              "action": "receipt"})

        # Send it to moneris and retrieve the receipt
        moneris_url = "https://gatewayt.moneris.com/chkt/request/request.php"
        r = requests.post(url=moneris_url, data=receipt)
        r.raise_for_status()
        rData = r.json()
        if (rData["response"]["success"] != "true"):
            return {
                'statusCode': 200,
                'headers': {
                    "x-custom-header": "my custom header value",
                    "Access-Control-Allow-Origin": "*"
                },
                'body': json.dumps({"success": False, "error": "Bad Request"})
            }

        # Getting service_id from most recent service at table
        cursor.execute(
            "SELECT service_id FROM service WHERE table_id = %s ORDER BY day_of_service DESC, service_started DESC LIMIT 1;", (table_id,))
        service_id = cursor.fetchone()[0]

        # removing the entries from the suborder table
        cart = rData["response"]["request"]["cart"]["items"]
        print(cart)
        total = 0
        for food in cart:

            # Get item from receipt (assume secure channel)
            item_quantity = int(food["quantity"])
            item_desc = food["description"]
            item_code = food["product_code"]

            # Valid food items, not the tip descriptor
            if item_code != "tip":
                # Get item_id from description, takes the first one in case of conflicts
                #print(item_desc)
                cursor.execute(
                    "SELECT item_id from Items WHERE item_desc = %s ORDER BY item_id DESC LIMIT 1;", (item_desc,))
                item_id = cursor.fetchone()[0]

                # Get existing quantity from suborder table
                cursor.execute(
                    "SELECT quantity from Suborder WHERE service_id = %s AND item_id = %s;", (service_id, item_id))
                exist_quantity = cursor.fetchone()[0]
                rev_q = exist_quantity - item_quantity
                # Remove from suborder table
                if (rev_q == 0):
                    cursor.execute(
                        "DELETE FROM Suborder WHERE service_id = %s and item_id = %s;", (service_id, item_id))
                else:
                    # Update
                    cursor.execute(
                        "UPDATE Suborder SET quantity = %s WHERE service_id = %s and item_id = %s;", (rev_q, service_id, item_id))
                # Increment total amt
                total += float(item_quantity) * float(food["unit_cost"])

            else:
                # Tip, nothing to process for payment and nothing to delete from suborder
                pass

        # Check to see if a payment already exists in the database, by counting the number of instances the service_id shows up in the
        # payment table
        cursor.execute(
            "SELECT count(*) FROM Payment WHERE service_id = %s;", (service_id,))
        # the 1 is added to mean the next person
        payment_id = cursor.fetchone()[0] + 1

        tax_rate = 1.13  # HST
        post_tax_total = total*tax_rate
        print(post_tax_total)

        # Now adding this to the payments table
        cursor.execute("INSERT INTO Payment VALUES (%s, %s, %s, %s, %s);",
                       (service_id, payment_id, 117, post_tax_total, "Moneris Pay"))

        # Commit changes
        # COMMENT OUT THIS LINE FOR TESTING ON AWS
        connection.commit()

        # close cursor, connection
        cursor.close()
        connection.close()

        return {
            'statusCode': 200,
            'headers': {
                "x-custom-header": "my custom header value",
                "Access-Control-Allow-Origin": "*"
            },
            # return final receipt to frontend
            'body': json.dumps({"success": True, "receipt": rData})
        }
    except Exception as err:
        print("Exception: " + str(err))
        print(traceback.format_exc())
        return {
            'statusCode': 500,
            'headers': {
                "x-custom-header": "my custom header value",
                "Access-Control-Allow-Origin": "*"
            },
            'body': json.dumps({"success": False, "error": "Exception"})
        }

    return {
        'statusCode': 500,
        'headers': {
            "x-custom-header": "my custom header value",
            "Access-Control-Allow-Origin": "*"
        },
        'body': json.dumps({"success": False, "error": "unknown"})
    }

