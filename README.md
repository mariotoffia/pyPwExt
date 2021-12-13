# PyPwExt

![example workflow](https://github.com/mariotoffia/pypwext/actions/workflows/push.yml/badge.svg)
[![PyPI version](https://badge.fury.io/py/pypwext.svg)](https://badge.fury.io/py/pypwext)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=pypwext&metric=alert_status)](https://sonarcloud.io/dashboard?id=pypwext)

This is a extension, decorators and other utilities that complements thew [AWS Lambda Powertools](https://awslabs.github.io/aws-lambda-powertools-python) library. It is centered around the following four **pillars**


1. Logging
```python
logger = PyPwExtLogger()

@logger.method(classification=InfoClassification.PII)
def subscribe(customer: Customer) -> Subscription:
    ...
```
2. Error handling
```python
errors = PyPwExtErrorHandler()

@errors.collect
def do_operation():
    raise PyPwExtHTTPError('Something went wrong', details={'foo': 'bar'})
```
3. HTTP and Lambda Communication
```python
http = PyPwExtHTTPSession() # Defaults with "sane" retries, exp back-off etc.

@http.method(
    method='POST',
    url='https://{STAGE}.execute-api.{AWS_REGION}.amazonaws.com/{api_version}/my-api'
    params= {'email':'{email}'},
    body='customer'
)
def send_offer(
    api_version:str, 
    email: str, 
    customer: Customer,
    response_code:HTTPStatus=HTTPStatus.OK, 
    response_body:str = ''
) -> str:
    ...
```
4. µService Support
```python
service = PyPwExtService()

@service.response
@event_parser(model=Order)
def handler(event: Order, context: LambdaContext):

    if not event.pypwext_id:
        raise StdPyPwExtError(
            code=HTTPStatus.BAD_REQUEST,
            message="Missing pypwext_id",
        )

    return PyPwExtResponse(
        status_code=HTTPStatus.OK,
        updated=[item for item in event.items],
        operation="create-order",            
    )
```


## Overview
This module contains the core functionality of the PyPwExt µService applications. 

:bulb: Each piece of functionality is implemented as an individual function and is **not** 
dependant on each other. Hence, it is up to the implementor to **choose** which ones to use.

It consists of **structural** and **semantic** elements to align the *µServices* when logging, 
error, input and output handling. It does **not** mandate any specific model when it comes to 
the content of the payloads sent back and forth. 

The only **reserved** return body element is *error*. But that is if you use `PyPwExtResponse` 
**and** `PyPwExtService.response` decorator. You may even omit that if you set the 
`@response(just_status_code=True)`, and that is the *default* behavior 😊

For example:
```python
service = PyPwExtService()
logger = PyPwExtLogger(service='my-service')

@logger.method(classification=InfoClassification.PII)
@service.response
def my_service(request):
    raise PyPwExtHTTPError(
        message='bad input',
        details={
            Operation: 'my-operation'
            'org_no': '7112234455'
        })
```

By default, this would return the following
```http
HTTP status code: 400
Body: None
```

If you instead set 

```python
@service.response(just_status_code=False)
```

it would return

```json
{
    "error": {
        "message": "bad input",
        "details": {
            "operation": "my-operation",
            "org_no": "7112234455"
        }
    }
}
```

## A extended example

The example below uses most of the features of the *PyPwExt* main types. Even though each feature supports quite a few configuration options to fit the exact purpose, it comes with many *"sane"* defaults. Hence, many variations can be avoided. But it is there when it is needed.

```python
logger = PyPwExtLogger(default_logger=True, service='my-service')
errors = PyPwExtErrorHandler()
service = PyPwExtService()
http = PyPwExtHTTPSession() # Defaults with "sane" retries, exp back-off etc.

class Customer(BaseMode, extra=Extra.allow)
    email: str
    age: Optional[int] = None

class Customers(BaseModel, extra=Extra.allow):
    Customers: List[Customer] = Field(default_factory=list)


@errors.collect
@logger.method(log_exception=False)
@http.method(
    method='POST',
    url='https://{STAGE}.execute-api.{AWS_REGION}.amazonaws.com/{api_version}/my-api'
    params= {'email':'{email}'},
    body='customer'
)
def send_offer(
    api_version:str, 
    email: str, 
    customer: Customer,
    response_code:HTTPStatus=HTTPStatus.OK, 
    response_body:str = ''
) -> str:

    # send offer to customer -> fail -> raise
    if response_code == HTTPStatus.OK:
        raise PyPwExtErrorWithReturn(
            code=HTTPStatus.BAD_REQUEST,
            message=f"Failed to send offer to customer: {email}",
            details={Operation: 'send_offer', 'customer': customer}
        )

    return email

@logger.method(type=LogEntryType.AUDIT, operation='send_offer')
@errors.collect(root=True)
@service.response
@event_parser(model=CustomerData)
def handler(event: CustomerData, ctx: LambdaContext) -> any:
    return PyPwExtResponse(
        status_code=HTTPStatus.OK,
        updated=list(filter(partial(is_not, None), [send_offer('1.0.0', c.email,c) for c in event])),
        operation="create-offer"
    )
```

Since, `@service.response` by default returns the "largest" status code (*otherwise `code_from_error=False`*). The above could, for example, produce the following response payload:

```json
{
    "updated": ["nisse@manpower.com"], 
    "operation": "create-offer", 
    "error": [
        {
            "code": 400, 
            "msg": "Failed to find record for customer: mario.toffia@pypwext.se", 
            "classification": "NA", 
            "details": {"operation": "send_offer", "customer": { "email": "mario.toffia@pypwext.se", "org_no": "1234567890" }}
        }, 
        {
            "code": 400, 
            "msg": "Failed to find record for customer: ivar@ikea.se", 
            "classification": "NA", 
            "details": {"operation": "send_offer", "customer": { "email": "ivar@ikea.se", "org_no": "0987654321" }}
        }
    ]
}
```

Since `@logger.method` is applied, it logs it using `DEBUG` verbosity at the entry, and `INFO` log the exit by default. However, it won't log the exception in the `send_offer` function since it would fill the log with cluttered information.

The `@http.method` automatically detects *AWS API* endpoints and uses *SigV4* by default. However, it is completely configurable in the `PyPwExtHTTPSession` constructor. 

Since no argument given in ``@service.response``, the ``PyPwExtResponse`` object is converted to an API Gateway response that supports either *REST* or *HTTPv2* version of the API Gateway. Thus the *JSON* payload is the *body* part of the response, and the *statusCode* is set to 402 (*NOT FOUND*) since that was the last collected error. Of course, you may override this behaviour if you want.

The *PyPwExt* also comes with an out of the box ``PyPwExtJSONEncoder``capable of handling many object types and
is extensible. For example, it adheres to ``base`` module protocols such as ``SupportsToJson`` and ``SupportsToCuratedDict`` (that also ``pydantic.BaseModel`` also exposes).

### A note on the ordering of the decorators

How decorators wrap the functions is basic *Python* knowledge. However, it is sometimes essential which order the function is decorated.

```python
from aws_lambda_powertools.utilities.data_classes import (
    event_source, 
    APIGatewayProxyEventV2
)

@event_source(data_class=APIGatewayProxyEventV2)
@logger.method
@errors.collect(root=True)
@service.response(just_status_code=False)
def handler(event: APIGatewayProxyEventV2,, context: LambdaContext):
    ...
```

1.  First, install a *root* collector so the `@service.response` may pick those errors and merge those with the response. 
    Therefore, the `@errors.collect` must be before (thus installs the collector for the `@service.response` to use).

2.  The intention of `@logger.method` is to log the `APIGatewayProxyEventV2` in addition to the `Response` object. It also logs
    any raised `PyPwExtError` object.

3.  Then, for the `@event_source` to get its data, parse it to an `APIGatewayProxyEventV2` object.


:bulb: **Hence, the decorator *"execution"* order is top-down and returns bottom-up. You decide what you want to happen!**

## Sample Typed µService

```python
class PyPwExtModel(BaseModel): # NOTE: You may use the @dataclass decorator instead of the BaseModel class
    pypwext_id: str
    """Unique trace id, to be passed in all systems and logged to make trails"""

class OrderItem(BaseModel):
    id: int
    quantity: int
    description: str

class Order(PyPwExtModel):
    id: int
    description: str
    items: List[OrderItem]
    optional_field: Optional[str]

logger = PyPwExtLogger()
metrics = Metrics() 
service = PyPwExtService()

@service.response
@logger.method
@metrics.log_metrics
@event_parser(model=Order)
def handler(event: Order, context: LambdaContext):

    if not event.pypwext_id:
        raise StdPyPwExtError(
            code=HTTPStatus.BAD_REQUEST,
            message="Missing pypwext_id",
        )

    return PyPwExtResponse(
        status_code=HTTPStatus.OK,
        updated=[item for item in event.items],
        operation="create-order",            
    )
```

The sample renders an API Gateway *body* response of:
```json
{
    "operation": "create-order",
    "updated": [{"id": 1015938732, "quantity": 1, "description": "item xpto"}]
}
```

It logs the objects in the payload and the response, and if any error occurs, if exception-log it automatically. It also records metrics for *my-service* in the namespace *my-namespace* as an example of setting the environment variables *POWERTOOLS_SERVICE_NAME* and *POWERTOOLS_METRICS_NAMESPACE* to *my-service* and *my-namespace* respectively.

### Sample Calling other HTTP endpoints

The *HTTP* module returns a pre-configured HTTP session that defaults. For example, it can configure the number of retries and the timeout and which methods and response codes should yield a retry.

When retrying, it uses an exponential back-off and handles temporal outages.

```python
with PyPwExtHTTPSession(logger=logger) as http:
    response = http.get(
        'https://api.openaq.org/v1/cities',
        params={'country': 'SE'}
    )
```

Below, do reconfigure the timeout and logs on request and response. It also reconfigures the number of retries to 3 and a higher back-off factor (wait longer time).

```python
logger = PyPwExtLogger()

with PyPwExtHTTPSession(
    PyPwExtHTTPAdapter(timeout=10, logger=logger),
    PyPwExtRetry(total=3, backoff_factor=2),
) as http:
    response = http.get(
        "https://en.wikipedia.org/w/api.php"
    )
```

If an *API Gateway* call is wanted. It is expected to be on the following form: *https://{api-gateway-id}.execute-api.{region}.amazonaws.com/....*. The *HTTP* module automatically configures a `BotoAWSRequestsAuth` and set it to the *request.auth* parameter using the *AWS_REGION* environment variable. Thus, this makes the request match a *SigV4* request and gets authenticated at the *API Gateway* using the *AWS_ACCESS_KEY_ID* and *AWS_SECRET_ACCESS_KEY*.

```python
    with PyPwExtHTTPSession(region='eu-north-1') as http:
    http.get(
        'https://abc123.execute-api.eu-north-1.amazonaws.com/dev/cities',
        params={'country': 'SE'}
    )
```

The above example overrides the *AWS_REGION* environment to *eu-north-1*.

**NOTE: Since the `PyPwExtHTTPSession` is a standard python library `HTTPSession`, it pools connections and so on and thus should be
cached to avoid the overhead of creating a new session for each request.**

The `PyPwExtHTTPSession` extension handles synchronous and asynchronous lambda calls with configurable retries and "sensible" defaults. It is possible to use them from code or decorated on the function.

The sample below invokes the lambda synchronously and passes custom parameters in the `LambdaContext` and nothing as the body. It has a default of 10 times before giving up.

```python
with PyPwExtHTTPSession() as http:
    result = http.func(url='mario-unit-test-function',params={'country': 'SE'})
```

#### HTTP Decorator Samples

It is possible to decorate a function with the *HTTP* decorator to make the *HTTP* call and process the response in method or make the decorator return the response. The latter automatically raises a `PyPwExtHTTPError` if the *HTTP* status code is 299 or greater.

The simplest one is to make the request declarative with no processing in function (i.e. not declare any of the `response`, `response_body` or `response_code` parameters in the function prototype).

```python
http = PyPwExtHTTPSession()

@http.method(url='https://{STAGE}.api.openaq.org/v1/cities', params={'country': '{country}'})
def cities(country:str) -> requests.Response:
    pass

try
    response = cities(country='SE') # This will call the site and return the response
    print(response.text)
except PyPwExtHTTPError as e:
    print(e.response_body)
```

It is possible to process the response in the function and manually handle errors. Supply with any of the "response" parameters. Make sure the declare the "response" parameters with defaults (e.g. `response = None`).

```python
http = PyPwExtHTTPSession()

@http.method(url='https://api.openaq.org/v1/cities', params={'country': '{country}'})
def cities(country:str, response_body:str = '', response_code:HTTPStatus = HTTPStatus.NOT_FOUND) -> str:
    if response_code == http.HTTPStatus.OK:
        return f'{country} has {response_body["count"]} cities'
    else:
        raise PyPwExtHTTPError(code=response_code, message=response_body)
```

The URL is formatted with parameters supplied to the function when *UPPERCASE* finds those as environment variables. It then makes the
call and passes the response to the function. The function may then process the response and return a string.

Since the `PyPwExtHTTPSession` is by default resolving AWS API gateway calls, it uses the `BotoAWSRequestsAuth` to set the credentials by creating a SigV4 request (it is possible to turn off this behaviour). 

```python
http = PyPwExtHTTPSession()

@http.method(
    method='POST',
    url='https://{gw_id}.execute-api.{AWS_REGION}.amazonaws.com/dev/cities',
    body='city'
)
def get_cities(gw_id: str, city: str, response: Optional[requests.Response] = None) -> Dict[str, Any]:
    """ Gets the cities from a specific country.
    
        Args:
            gw_id:  The API Gateway ID
            city:   The body containing the country to fetch.
                    for example: `{"country": "SE"}`


        Returns:
            The response body.
    """
    return {
        'country': country,        
        'result': json.loads(response.text)
    }

value = get_cities('abc123', 'SE', 'the body')
```

#### HTTP Decorator Lambda Samples
It is possible to invoke the lambda function synchronously (_FUNC_) and asynchronously (_EVENT_). Given the following lambda function
```python
def lambda_handler(event, context):
    if event.get('country'):
        country = event['country']
    else:
        country = context.client_context.custom['country'] # contrives to show that you can use custom data in the context
        
    result = requests.get(
        'https://api.openaq.org/v1/cities', params={'country':country}
    )
    
    if result.status_code != 200:
        raise ValueError(f'Failed to get cities result: {result.status_code}')
    
    return json.loads(result.text)
```

Invoking the lambda using _FUNC_ (synchronous) is as simple as:
```python
@http.method(
    method='FUNC',
    url='arn:aws:lambda:eu-west-1:010711114025:function:mario-unit-test-function',
    params={'country': '{country}'}
)
def get_cities(country: str, response: LambdaResponse = None) -> str:
    if response.StatusCode == HTTPStatus.OK.value:
        return response.payload_as_text()
    else:
        raise PyPwExtHTTPError(
            code=response.StatusCode,
            message=f'Failed to get cities from {country}',
            details={
                'error': response.payload_as_text()
            }
        )

value = get_cities(country='SE')
```

:bulb: **NOTE:** The lambda function is invoked synchronously. Hence, the `response` is a `LambdaResponse` object instead of the `requests.Response` object. Therefore, thee returned payload from the lambda.

If you'd like to invoke the lambda asynchronously, you can use the _EVENT_ method. The following example is for a lambda function that is invoked asynchronously.

```python
@http.method(method='EVENT', url='{STAGE}-function:mario-unit-test-function', body='body')
def get_cities(body: Dict[str, Any], response: LambdaResponse = None) -> str:
    if response.StatusCode == HTTPStatus.ACCEPTED.value:
        return json.dumps(response.ResponseMetadata)
    else:
        raise PyPwExtHTTPError(
            code=response.StatusCode,
            message=f'Failed to get cities from {body}',
            details={
                'error': response.FunctionError
            }
        )

value = get_cities({'country': 'SE'})
```

Since it is asynchronous, no custom `LambdaContext` can be used. Note that the successful invocation is indicated by the `StatusCode` being `202` (Accepted). Since the lambda cannot return anything, the `LambdaResponse.Payload` do not contain anything.

It is still possible to use lambda's `response_body` and `response_code` parameters. The `response_body` for _EVENT_ type will be `json.dumps(response.ResponseMetadata)`. When creating a `PyPwExtHTTPSession` it is possible to override the PyPwExt defaults for the boto-core `Config` object. The default is:

```python
Config(
            region_name=self.region, # region is either manual set or AWS_REGION env var
            connect_timeout=60,
            read_timeout=60,
            retries={
                'total_max_attempts': 10,
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )
```

If you supply a `Config` object, it is merged over the defaults.

### Sample logging output

The logger, independent if it is decorated or used directly, forces few new fields

* level
* timestamp
* message
* service
* classification
* type
* operation

Additionally, if you enable log lambda context, it adds a set of function_* fields. If x-ray is enabled, it logs that as well. The below entry also adds a *correlation_id* of the REST API Gateway request-id.

```python
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def handler(event, context):
    return app.resolve(event, context)
```

Sample log entry:

```json
{
    "level": "ERROR",
    "location": "get_pep_by_ssn:555",
    "message": {
        "msg": "Exception in get_pep_by_ssn",
        "args": {
            "person_ssn": "197105180090"
        }
    },
    "timestamp": "2021-11-24 13:38:50,673+0000",
    "service": "know_your_customer",
    "classification": "PII",
    "type": "STD",
    "cold_start": true,
    "function_name": "test_func",
    "function_memory_size": "1024",
    "function_arn": "arn:aws:lambda:eu-west-1:010711114025:function:test_func",
    "function_request_id": "a89efe17-7a9e-49f8-9b4c-f00abd7b2ac8",
    "correlation_id": "1db848fb-bf8b-4b5d-b2ad-61e2175181b4",
    "operation": "get-user-info",
    "exception": "...exception...",
    "exception_name": "StdPyPwExtError",
    "xray_trace_id": "1-619e4067-62471735a4cf522db5720c7e"
}
```

## Philosophy

The *PyPwExt* is a µService framework designed to be *opt-in* instead of *opt-out*. It means
that you may always choose to use the functionality instead of *REQUIRED* to use it. So, for example, if you
have decorated a ``handler`` with `@pypwext_response`, you always have the option to bypass it, e.g. returning
your own custom *JSON* response.

```python
logger = PyPwExtLogger(service='my-service')
service = PyPwExtService()

@logger.method
@service.response
def handler(customers: List[str]):
    return json.dumps({
        "statusCode": 200,
        "body": {
            "updated": list(filter(partial(is_not, None), [send_offer(c) for c in customers])),
            Operation: "create-offer"
        }
    })
```

The above still logs if any error occurs and returns a standardized response upon exception but completely bypassing
response handling. Instead, it returns the *JSON* response as-is.

You may use small parts or the whole package, and each decorator can be used separately. It is also possible to access parts
from code such as the ``@errors.collect`` decorator do expose currently collected errors through. `get_current_collector()` 
where actions may be taken due to collected errors down the chain. Or you may choose to clear errors and let the decorator
process as those have never been collected.

The important part of *PyPwExt* is that the µServices are semantically and structurally the same. Therefore some
base types and reserved *keywords* do exist. For example, when a particular operation is commenced, the ``Operation`` key facades the value. For example:

```python
logger = PyPwExtLogger(service='my-service')

@logger.method(operation='create-offer')
def create_offer(...) -> ...:
    ...
```

The above logs the entry with **DEBUG** and exit with **INFO** level automatically with the `{"operation": "create-offer"}`.
It also uses standardized keywords such as `Return` and `Arguments` to log the entry arguments and return values.

Using standardized keywords makes it easier to understand and search in the logs.

Of course, the above could be done in code, but not recommended.

```python
logger.info({
        Operation: "pay",
        Classification: InfoClassification.CORPORATE_SENSITIVE_INFO,
        LogType: LogEntryType.AUDIT,
        Arguments: {"amount": amount, "credit_card_id": credit_card_id}})
```

The above sample uses constants defined in the ``base`` module. Since the ``PyPwExtLogger`` is based on the Powertools logger, it is quite possible to, e.g. include ``@logger.inject_lambda_context(log_event=True)`` to log the Lambda event including lambda context variables automatically.

## Dependencies

PyPwExt is heavily dependant on the [AWS Lambda Powertools](https://awslabs.github.io/aws-lambda-powertools-python/latest/) where the ``PyPwExtLogger`` derives from the Powertools ``Logger`` and ``PyPwExtReturn``understand API Proxy ``Response`` natively.

An optional dependency that plugs right in is [Pydantic](https://pydantic-docs.helpmanual.io/). It is a model and validation framework that can validate the input and output of the microservice. In addition, the [AWS Lambda Powertools](https://awslabs.github.io/aws-lambda-powertools-python/latest/) relies on *Pydantic* when using the [Typing Module](https://awslabs.github.io/aws-lambda-powertools-python/latest/utilities/typing/>).

## Setup development environment

1. Create a virtual python environment `python -m venv .venv`.
2. Activate it by `. .venv/bin/activate`.
3. Install the dependencies by `make dependencies`.

Now the environment is ready to use.
