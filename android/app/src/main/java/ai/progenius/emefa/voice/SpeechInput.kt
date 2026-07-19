package ai.progenius.emefa.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.util.Locale

class SpeechInput(
    context: Context,
    private val onListeningChanged: (Boolean) -> Unit,
    private val onTranscript: (String) -> Unit,
    private val onError: (String) -> Unit,
) : RecognitionListener {
    private val recognizer: SpeechRecognizer? =
        if (SpeechRecognizer.isRecognitionAvailable(context)) {
            SpeechRecognizer.createSpeechRecognizer(context).also {
                it.setRecognitionListener(this)
            }
        } else {
            null
        }

    private val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.FRENCH.toLanguageTag())
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
    }

    fun start() {
        val activeRecognizer = recognizer
        if (activeRecognizer == null) {
            onError("La reconnaissance vocale n’est pas disponible sur ce téléphone.")
            return
        }
        onListeningChanged(true)
        activeRecognizer.startListening(intent)
    }

    fun stop() {
        recognizer?.stopListening()
        onListeningChanged(false)
    }

    fun destroy() {
        recognizer?.destroy()
    }

    override fun onReadyForSpeech(params: Bundle?) = Unit
    override fun onBeginningOfSpeech() = Unit
    override fun onRmsChanged(rmsdB: Float) = Unit
    override fun onBufferReceived(buffer: ByteArray?) = Unit
    override fun onEndOfSpeech() = onListeningChanged(false)

    override fun onError(error: Int) {
        onListeningChanged(false)
        val message = when (error) {
            SpeechRecognizer.ERROR_NO_MATCH -> "Je n’ai pas compris. Vous pouvez réessayer."
            SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Je n’ai rien entendu."
            SpeechRecognizer.ERROR_NETWORK,
            SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "La reconnaissance vocale est temporairement indisponible."
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "L’accès au microphone est nécessaire pour parler à EMEFA."
            else -> "La saisie vocale a rencontré un problème."
        }
        onError(message)
    }

    override fun onResults(results: Bundle?) {
        onListeningChanged(false)
        val transcript = results
            ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            ?.firstOrNull()
        if (transcript.isNullOrBlank()) {
            onError("Je n’ai pas compris. Vous pouvez réessayer.")
        } else {
            onTranscript(transcript)
        }
    }

    override fun onPartialResults(partialResults: Bundle?) = Unit
    override fun onEvent(eventType: Int, params: Bundle?) = Unit
}
