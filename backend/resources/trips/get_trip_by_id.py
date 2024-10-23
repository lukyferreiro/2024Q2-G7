import json
import boto3
from decimal import Decimal
import os
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
import base64
import json

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o) if o % 1 > 0 else int(o)
        return super(DecimalEncoder, self).default(o)
    
def build_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'OPTIONS, POST, GET',
            'Access-Control-Allow-Headers': 'Content-Type',
        },
        'body': json.dumps(body)
    }

def decode_jwt(token):
    try:
        header, payload, signature = token.split('.')
        decoded_payload = json.loads(base64.urlsafe_b64decode(payload + "==").decode('utf-8'))
        return decoded_payload
    except Exception as e:
        raise Exception(f"Error decoding token: {str(e)}")

def convert_sets_to_lists(data):
    if isinstance(data, set):
        return list(data)
    elif isinstance(data, dict):
        return {key: convert_sets_to_lists(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_sets_to_lists(item) for item in data]
    return data

def main(event, context):
    path_params = event.get('pathParameters') or {}
    trip_id = path_params.get('trip_id')

    headers = event['headers']
    if not headers:
        return build_response(401, {'error': 'Authorization header missing'})

    auth_header = headers.get('Authorization', '')
    if not auth_header:
        return build_response(401, {'error': 'Authorization header missing'})

    # "Bearer <token>"
    token_parts = auth_header.split(' ')
    if len(token_parts) != 2 or token_parts[0].lower() != 'bearer':
        return build_response(401, {'error': 'Invalid Authorization header format'})

    token = token_parts[1]
    try:
        decoded_token = decode_jwt(token)
    except Exception as e:
        return build_response(401, {'error': str(e)})
    
    user_id = decoded_token['sub']

    dynamodb = boto3.resource('dynamodb')
    table_name = os.getenv('TRIPS_TABLE_NAME', 'trips-table')
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(Key={ 'user_id': user_id, 'id': trip_id })
        
        trip = response.get('Item', None)  

        if trip == None:
            return build_response(404, {'error': 'Trip not found'})
        
    except Exception as e:
        return build_response(500, {'error': f'Failed to get trip: {str(e)}'})
    
    experience_ids = list(trip.get('experiences', set()))  # Convertimos el set a lista
    
    experience_details = []
    
    dynamodb = boto3.resource('dynamodb')
    experiences_table = os.getenv('EXPERIENCES_TABLE_NAME', 'experiences-table')
    table = dynamodb.Table(experiences_table)
    STATUS = 'VERIFIED'

    for experience_id in experience_ids:
        try:
            response = table.query(
                IndexName='ByStatusIndex',  
                KeyConditionExpression=Key('status').eq(STATUS) & Key('id').eq(experience_id)
            )
            
            if 'Items' in response and len(response['Items']) > 0:
                experience_details.append(response['Items'][0]) 
        except Exception as e:
            return build_response(500, {'error': f'Failed to get trip experience: {str(e)}'})
    
    trip_item_complete = {
        'user_id': trip['user_id'],
        'id': trip['id'],
        'name': trip['name'],
        'start_date': trip['start_date'],
        'end_date': trip['end_date'],
        'description': trip['description'],
        'experiences': experience_details  
    }
    
    return build_response(200, trip_item_complete)
