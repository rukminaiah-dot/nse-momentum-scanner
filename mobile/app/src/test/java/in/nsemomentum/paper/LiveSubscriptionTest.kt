package com.nsemomentum.paper

import com.google.protobuf.CodedOutputStream
import java.io.ByteArrayOutputStream
import java.time.Instant
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.collect
import okhttp3.*
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.ByteString
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class LiveSubscriptionTest {
    private fun message(write:(CodedOutputStream)->Unit):ByteArray {
        val b=ByteArrayOutputStream();val out=CodedOutputStream.newInstance(b);write(out);out.flush();return b.toByteArray()
    }
    private fun frame(key:String):ByteString {
        val now=Instant.now().toEpochMilli()
        val ltpc=message { it.writeDouble(1,100.0);it.writeInt64(2,now);it.writeDouble(4,99.0) }
        val feed=message { it.writeByteArray(1,ltpc) }
        val entry=message { it.writeString(1,key);it.writeByteArray(2,feed) }
        return ByteString.of(*message { it.writeByteArray(2,entry);it.writeInt64(3,now) })
    }
    @Test fun addingCommodityAndRemovingItKeepsTheStockSocketAndConnectionEpoch()=runBlocking {
        val server=MockWebServer();server.start()
        server.enqueue(MockResponse().setBody("""{"status":"success","data":{"authorized_redirect_uri":"wss://feed.upstox.com/test"}}"""))
        val commands=Channel<JSONObject>(10);val states=Channel<LivePriceState>(20)
        var initialFrameSent=false
        var connections=0;lateinit var listener:WebSocketListener;lateinit var socket:WebSocket
        val factory=WebSocket.Factory { request,l ->
            connections++;listener=l
            socket=object:WebSocket {
                override fun request()=request
                override fun queueSize()=0L
                override fun send(text:String)=false
                override fun send(bytes:ByteString):Boolean {
                    val sent=commands.trySend(JSONObject(bytes.utf8())).isSuccess
                    // Immediate provider response must never appear with connectionId=0.
                    if(!initialFrameSent) { initialFrameSent=true;l.onMessage(this,frame("NSE_EQ|TEST")) }
                    return sent
                }
                override fun close(code:Int,reason:String?)=true
                override fun cancel() {}
            }
            l.onOpen(socket,Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(101).message("Switching").build())
            socket
        }
        val key="NSE_EQ|TEST";val commodity="MCX_FO|1234"
        val desired=MutableStateFlow(setOf(key))
        val client=UpstoxLivePrices(apiBase=server.url("").toString().trimEnd('/'),webSockets=factory)
        val job=launch(Dispatchers.Default) { client.stream("test",setOf(key),requested=desired).collect { states.send(it) } }
        suspend fun quote():LivePriceState=withTimeout(5000) { var state=states.receive();while(state.quotes[key]==null) state=states.receive();state }
        try {
            withTimeout(5000) { assertEquals("sub",commands.receive().getString("method")) }
            listener.onMessage(socket,frame(key));val first=quote();assertNotEquals(0L,first.connectionId)
            desired.value=setOf(key,commodity)
            listener.onMessage(socket,frame(key))
            withTimeout(5000) { val add=commands.receive();assertEquals("sub",add.getString("method"));assertEquals(commodity,add.getJSONObject("data").getJSONArray("instrumentKeys").getString(0)) }
            val second=quote();assertEquals(first.connectionId,second.connectionId)
            desired.value=setOf(key)
            listener.onMessage(socket,frame(key))
            withTimeout(5000) { assertEquals("unsub",commands.receive().getString("method")) }
            assertEquals(first.connectionId,quote().connectionId);assertEquals(1,connections)
        } finally { job.cancelAndJoin();server.shutdown() }
    }
}

