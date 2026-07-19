package ai.progenius.emefa

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import ai.progenius.emefa.conversation.ConversationState
import ai.progenius.emefa.network.EmefaApi
import ai.progenius.emefa.storage.DevicePreferences
import ai.progenius.emefa.voice.SpeechInput
import kotlinx.coroutines.launch

private data class ChatMessage(val author: String, val text: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { EmefaApplication() }
    }
}

@Composable
private fun EmefaApplication() {
    val colors = lightColorScheme(
        primary = Color(0xFF006B5E),
        onPrimary = Color.White,
        primaryContainer = Color(0xFFA7F2DF),
        background = Color(0xFFF5FBF8),
        surface = Color.White,
    )
    val context = LocalContext.current
    val preferences = remember { DevicePreferences(context) }
    var token by remember { mutableStateOf(preferences.token) }

    MaterialTheme(colorScheme = colors) {
        Surface(modifier = Modifier.fillMaxSize()) {
            if (token == null) {
                EnrollmentScreen(preferences) { enrolledToken -> token = enrolledToken }
            } else {
                ConversationScreen(
                    serverUrl = preferences.serverUrl,
                    token = requireNotNull(token),
                    onDisconnect = {
                        preferences.clearEnrollment()
                        token = null
                    },
                )
            }
        }
    }
}

@Composable
private fun EnrollmentScreen(
    preferences: DevicePreferences,
    onEnrolled: (String) -> Unit,
) {
    var serverUrl by remember { mutableStateOf(preferences.serverUrl) }
    var deviceName by remember { mutableStateOf("Téléphone de Claude") }
    var enrollmentCode by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("EMEFA", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
        Text("Connexion privée de votre téléphone", color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(24.dp))
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = serverUrl,
                    onValueChange = { serverUrl = it },
                    label = { Text("Adresse sécurisée du serveur") },
                    placeholder = { Text("https://emefa.exemple.com") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = deviceName,
                    onValueChange = { deviceName = it },
                    label = { Text("Nom du téléphone") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = enrollmentCode,
                    onValueChange = { enrollmentCode = it },
                    label = { Text("Code d’activation") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Button(
                    enabled = !busy && serverUrl.isNotBlank() && deviceName.isNotBlank() && enrollmentCode.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        busy = true
                        error = null
                        scope.launch {
                            runCatching {
                                EmefaApi(serverUrl).enroll(deviceName.trim(), enrollmentCode)
                            }.onSuccess { enrollment ->
                                preferences.saveEnrollment(serverUrl, enrollment.deviceId, enrollment.token)
                                enrollmentCode = ""
                                onEnrolled(enrollment.token)
                            }.onFailure { failure ->
                                error = failure.message ?: "Connexion impossible."
                            }
                            busy = false
                        }
                    },
                ) {
                    Text(if (busy) "Connexion…" else "Activer EMEFA")
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            "Le code d’activation n’est utilisé qu’une fois. Votre clé de fournisseur IA reste sur le serveur.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun ConversationScreen(
    serverUrl: String,
    token: String,
    onDisconnect: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf(ConversationState()) }
    var notice by remember { mutableStateOf<String?>(null) }
    var sending by remember { mutableStateOf(false) }
    val messages = remember { mutableStateListOf<ChatMessage>() }
    val api = remember(serverUrl) { EmefaApi(serverUrl) }

    val speech = remember {
        SpeechInput(
            context = context,
            onListeningChanged = { listening ->
                state = if (listening) state.startListening() else state.stopListening()
            },
            onTranscript = { transcript ->
                state = state.withSpeechTranscript(transcript)
                notice = null
            },
            onError = { message -> notice = message },
        )
    }
    DisposableEffect(speech) { onDispose { speech.destroy() } }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) speech.start()
        else notice = "Autorisez le microphone pour utiliser la saisie vocale."
    }

    fun requestSpeech() {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            speech.start()
        } else {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 20.dp, vertical = 20.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text("EMEFA", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
                Text("Votre assistante personnelle", color = MaterialTheme.colorScheme.primary)
            }
            TextButton(onClick = onDisconnect) { Text("Déconnecter") }
        }
        Spacer(Modifier.height(16.dp))

        Column(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (messages.isEmpty()) {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                    Column(Modifier.padding(18.dp)) {
                        Text("Bonjour Claude", fontWeight = FontWeight.SemiBold)
                        Text("Écrivez votre demande ou appuyez sur Parler. Relisez votre phrase avant de l’envoyer.")
                    }
                }
            }
            messages.forEach { message ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp)) {
                        Text(message.author, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                        Text(message.text)
                    }
                }
            }
        }

        notice?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(vertical = 8.dp)) }
        OutlinedTextField(
            value = state.draft,
            onValueChange = { state = state.copy(draft = it) },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Votre demande") },
            minLines = 2,
            maxLines = 5,
        )
        Spacer(Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(
                onClick = { if (state.isListening) speech.stop() else requestSpeech() },
                enabled = !sending,
                modifier = Modifier.weight(1f),
            ) { Text(if (state.isListening) "Arrêter" else "Parler") }
            Spacer(Modifier.width(12.dp))
            Button(
                onClick = {
                    val text = state.draft.trim()
                    if (text.isEmpty()) return@Button
                    messages += ChatMessage("Vous", text)
                    state = state.copy(draft = "")
                    notice = null
                    sending = true
                    scope.launch {
                        runCatching { api.run(text, token) }
                            .onSuccess { reply ->
                                when (reply.status) {
                                    "completed" -> messages += ChatMessage("EMEFA", reply.answer ?: "Réponse vide.")
                                    "confirmation_required" -> notice = "Confirmation requise pour ${reply.pendingAction ?: "cette action"}."
                                    "blocked" -> notice = "Cette action est bloquée dans la version actuelle."
                                    else -> notice = reply.error ?: "EMEFA n’a pas pu terminer la demande."
                                }
                            }
                            .onFailure { failure -> notice = failure.message ?: "Connexion au serveur impossible." }
                        sending = false
                    }
                },
                enabled = state.draft.isNotBlank() && !state.isListening && !sending,
                modifier = Modifier.weight(1f),
            ) { Text(if (sending) "Envoi…" else "Envoyer") }
        }
    }
}
