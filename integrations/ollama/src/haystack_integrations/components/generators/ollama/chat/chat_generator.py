from typing import Any, Callable, Dict, List, Optional

from haystack import component
from haystack.dataclasses import ChatMessage, StreamingChunk

from ollama import Client


@component
class OllamaChatGenerator:
    """
    Supports models running on Ollama, such as llama2 and mixtral.  Find the full list of supported models
    [here](https://ollama.ai/library).

    Usage example:
    ```python
    from haystack_integrations.components.generators.ollama import OllamaChatGenerator
    from haystack.dataclasses import ChatMessage

    generator = OllamaChatGenerator(model="zephyr",
                                url = "http://localhost:11434",
                                generation_kwargs={
                                "num_predict": 100,
                                "temperature": 0.9,
                                })

    messages = [ChatMessage.from_system("\nYou are a helpful, respectful and honest assistant"),
    ChatMessage.from_user("What's Natural Language Processing?")]

    print(generator.run(messages=messages))
    ```
    """

    def __init__(
        self,
        model: str = "orca-mini",
        url: str = "http://localhost:11434",
        generation_kwargs: Optional[Dict[str, Any]] = None,
        timeout: int = 120,
        streaming_callback: Optional[Callable[[StreamingChunk], None]] = None,
    ):
        """
        :param model:
            The name of the model to use. The model should be available in the running Ollama instance.
        :param url:
            The URL of a running Ollama instance.
        :param generation_kwargs:
            Optional arguments to pass to the Ollama generation endpoint, such as temperature,
            top_p, and others. See the available arguments in
            [Ollama docs](https://github.com/jmorganca/ollama/blob/main/docs/modelfile.md#valid-parameters-and-values).
        :param timeout:
            The number of seconds before throwing a timeout error from the Ollama API.
        :param streaming_callback:
            A callback function that is called when a new token is received from the stream.
            The callback function accepts StreamingChunk as an argument.
        """

        self.timeout = timeout
        self.generation_kwargs = generation_kwargs or {}
        self.url = url
        self.model = model
        self.streaming_callback = streaming_callback

        self._client = Client(host=self.url, timeout=self.timeout)

    def _message_to_dict(self, message: ChatMessage) -> Dict[str, str]:
        return {"role": message.role.value, "content": message.content}

    def _build_message_from_ollama_response(self, ollama_response: Dict[str, Any]) -> ChatMessage:
        """
        Converts the non-streaming response from the Ollama API to a ChatMessage.
        """
        message = ChatMessage.from_assistant(content=ollama_response["message"]["content"])
        message.meta.update({key: value for key, value in ollama_response.items() if key != "message"})
        return message

    def _convert_to_streaming_response(self, chunks: List[StreamingChunk]) -> Dict[str, List[Any]]:
        """
        Converts a list of chunks response required Haystack format.
        """

        replies = [ChatMessage.from_assistant("".join([c.content for c in chunks]))]
        meta = {key: value for key, value in chunks[0].meta.items() if key != "message"}

        return {"replies": replies, "meta": [meta]}

    def _build_chunk(self, chunk_response: Any) -> StreamingChunk:
        """
        Converts the response from the Ollama API to a StreamingChunk.
        """
        content = chunk_response["message"]["content"]
        meta = {key: value for key, value in chunk_response.items() if key != "message"}
        meta["role"] = chunk_response["message"]["role"]

        chunk_message = StreamingChunk(content, meta)
        return chunk_message

    def _handle_streaming_response(self, response) -> List[StreamingChunk]:
        """
        Handles Streaming response cases
        """
        chunks: List[StreamingChunk] = []
        for chunk in response:
            chunk_delta: StreamingChunk = self._build_chunk(chunk)
            chunks.append(chunk_delta)
            if self.streaming_callback is not None:
                self.streaming_callback(chunk_delta)
        return chunks

    @component.output_types(replies=List[ChatMessage])
    def run(
        self,
        messages: List[ChatMessage],
        generation_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Runs an Ollama Model on a given chat history.

        :param messages:
            A list of ChatMessage instances representing the input messages.
        :param generation_kwargs:
            Optional arguments to pass to the Ollama generation endpoint, such as temperature,
            top_p, etc. See the
            [Ollama docs](https://github.com/jmorganca/ollama/blob/main/docs/modelfile.md#valid-parameters-and-values).
        :param streaming_callback:
            A callback function that will be called with each response chunk in streaming mode.
        :returns: A dictionary with the following keys:
            - `replies`: The responses from the model
        """
        generation_kwargs = {**self.generation_kwargs, **(generation_kwargs or {})}

        stream = self.streaming_callback is not None
        messages = [self._message_to_dict(message) for message in messages]
        response = self._client.chat(model=self.model, messages=messages, stream=stream, options=generation_kwargs)

        if stream:
            chunks: List[StreamingChunk] = self._handle_streaming_response(response)
            return self._convert_to_streaming_response(chunks)

        return {"replies": [self._build_message_from_ollama_response(response)]}
