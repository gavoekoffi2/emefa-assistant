package ai.progenius.emefa.conversation

data class ConversationState(
    val draft: String = "",
    val isListening: Boolean = false,
) {
    fun startListening(): ConversationState = copy(isListening = true)

    fun stopListening(): ConversationState = copy(isListening = false)

    fun withSpeechTranscript(transcript: String): ConversationState {
        if (transcript.isBlank()) return stopListening()
        return copy(draft = transcript, isListening = false)
    }
}
