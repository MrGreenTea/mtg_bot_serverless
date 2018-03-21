import elasticsearch
import logging

LOGGER = logging.getLogger(__name__)


def connect_elastic(elastic_end_point):
    LOGGER.info('Connecting to the ES Endpoint %s', elastic_end_point)
    try:
        return elasticsearch.Elasticsearch(
            hosts=[{'host': elastic_end_point, 'port': 443}],
            use_ssl=True,
            verify_certs=True,
            connection_class=elasticsearch.RequestsHttpConnection)
    except Exception as error:
        LOGGER.error("Unable to connect to %s", elastic_end_point, exc_info=error)
        raise


def ensure_index(elastic_client: elasticsearch.Elasticsearch, index_name: str):
    if not elastic_client.indices.exists(index_name):
        elastic_client.indices.create(index_name)

