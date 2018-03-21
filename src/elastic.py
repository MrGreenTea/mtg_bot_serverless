"""Module for connecting and writing to elastic search."""
import logging

from vendored import elasticsearch

LOGGER = logging.getLogger(__name__)


def connect_elastic(end_point):
    """Tries to connect to elastic instance at end_point"""
    LOGGER.info('Connecting to the ES Endpoint %s', end_point)
    try:
        return elasticsearch.Elasticsearch(
            hosts=[{'host': end_point, 'port': 443}],
            use_ssl=True,
            verify_certs=True,
            connection_class=elasticsearch.RequestsHttpConnection)
    except Exception as error:
        LOGGER.critical("Unable to connect to %s", end_point, exc_info=error)
        raise


def ensure_index(elastic_client: elasticsearch.Elasticsearch, index_name: str):
    """Makes sure the index with index_name exists."""
    if not elastic_client.indices.exists(index_name):
        elastic_client.indices.create(index_name)
