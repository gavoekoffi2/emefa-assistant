package ai.progenius.emefa.network

import com.sun.net.httpserver.HttpServer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test
import java.net.InetSocketAddress

class EmefaApiIntegrationTest {
    @Test
    fun enrollAndRunUseExpectedHttpContract() = runBlocking {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/v1/devices/enroll") { exchange ->
            assertEquals("POST", exchange.requestMethod)
            val body = exchange.requestBody.bufferedReader().use { it.readText() }
            check(body.contains("ONE-TIME"))
            val response = """{"device_id":"device-1","token":"secret-token"}"""
            exchange.sendResponseHeaders(201, response.toByteArray().size.toLong())
            exchange.responseBody.use { it.write(response.toByteArray()) }
        }
        server.createContext("/v1/agent/runs") { exchange ->
            assertEquals("Bearer secret-token", exchange.requestHeaders.getFirst("Authorization"))
            val response = """{"status":"completed","turns":1,"answer":"Bonjour Claude","pending_action":null,"error":null}"""
            exchange.sendResponseHeaders(200, response.toByteArray().size.toLong())
            exchange.responseBody.use { it.write(response.toByteArray()) }
        }
        server.start()
        try {
            val api = EmefaApi("http://127.0.0.1:${server.address.port}")
            val enrollment = api.enroll("Claude", "ONE-TIME")
            val reply = api.run("Bonjour", enrollment.token)

            assertEquals("device-1", enrollment.deviceId)
            assertEquals("secret-token", enrollment.token)
            assertEquals("completed", reply.status)
            assertEquals("Bonjour Claude", reply.answer)
        } finally {
            server.stop(0)
        }
    }
}
