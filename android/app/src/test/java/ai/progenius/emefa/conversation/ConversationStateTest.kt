package ai.progenius.emefa.conversation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ConversationStateTest {
    @Test
    fun speechTranscriptBecomesEditableDraft() {
        val state = ConversationState().withSpeechTranscript("Bonjour EMEFA")

        assertEquals("Bonjour EMEFA", state.draft)
        assertFalse(state.isListening)
    }

    @Test
    fun listeningStateIsExplicit() {
        val listening = ConversationState().startListening()
        assertTrue(listening.isListening)

        val stopped = listening.stopListening()
        assertFalse(stopped.isListening)
    }

    @Test
    fun blankSpeechDoesNotEraseExistingDraft() {
        val state = ConversationState(draft = "Texte existant")

        assertEquals("Texte existant", state.withSpeechTranscript("  ").draft)
    }
}
