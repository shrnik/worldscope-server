from bullmq import Queue

import redis_connection

image_processing_queue = Queue("imageProcessingQueue", {
    "connection": redis_connection.redis_connection_options
})

results_queue = Queue("resultsQueue", {
    "connection": redis_connection.redis_connection_options
})