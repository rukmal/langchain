"""Wrapper around Pinecone vector database."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Iterable, List, Optional, Tuple

from langchain.docstore.document import Document
from langchain.embeddings.base import Embeddings
from langchain.vectorstores.base import VectorStore


class Pinecone(VectorStore):
    """Wrapper around Pinecone vector database.

    To use, you should have the ``pinecone-client`` python package installed.

    Example:
        .. code-block:: python

            import pinecone
            from langchain.vectorstores import Pinecone
            vectorstore = Pinecone(pinecone_index, embedding_function, "text_key")
    """

    def __init__(
        self,
        index: Any,
        embedding_function: Callable,
        text_key: str,
    ):
        """Initialize with Pinecone client."""
        try:
            import pinecone
        except ImportError:
            raise ValueError(
                "Could not import pinecone python package. "
                "Please it install it with `pip install pinecone-client`."
            )
        if not isinstance(index, pinecone.index.Index):
            raise ValueError(
                f"client should be an instance of pinecone.index.Index, "
                f"got {type(index)}"
            )
        self._index = index
        self._embedding_function = embedding_function
        self._text_key = text_key

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        namespace: Optional[str] = None,
    ) -> List[str]:
        """Run more texts through the embeddings and add to the vectorstore.

        Args:
            texts: Iterable of strings to add to the vectorstore.
            metadatas: Optional list of metadatas associated with the texts.
            namespace: Optional pinecone namespace to add the texts to.

        Returns:
            List of ids from adding the texts into the vectorstore.

        """
        # Embed and create the documents
        docs = []
        ids = []
        for i, text in enumerate(texts):
            id = str(uuid.uuid4())
            embedding = self._embedding_function(text)
            metadata = metadatas[i] if metadatas else {}
            metadata[self._text_key] = text
            docs.append((id, embedding, metadata))
            ids.append(id)
        # upsert to Pinecone
        self._index.upsert(vectors=docs, namespace=namespace)
        return ids

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        namespace: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        """Return pinecone documents most similar to query, along with scores.

        Args:
            query: Text to look up documents similar to.
            k: Number of Documents to return. Defaults to 4.
            namespace: Namespace to search in. Default will search in '' namespace.

        Returns:
            List of Documents most similar to the query and score for each
        """
        query_obj = self._embedding_function(query)
        docs = []
        results = self._index.query(
            [query_obj], top_k=k, include_metadata=True, namespace=namespace
        )
        for res in results["matches"]:
            metadata = res["metadata"]
            text = metadata.pop(self._text_key)
            docs.append((Document(page_content=text, metadata=metadata), res["score"]))
        return docs

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        namespace: Optional[str] = None,
    ) -> List[Document]:
        """Return pinecone documents most similar to query.

        Args:
            query: Text to look up documents similar to.
            k: Number of Documents to return. Defaults to 4.
            namespace: Namespace to search in. Default will search in '' namespace.

        Returns:
            List of Documents most similar to the query and score for each
        """
        query_obj = self._embedding_function(query)
        docs = []
        results = self._index.query(
            [query_obj], top_k=k, include_metadata=True, namespace=namespace
        )
        for res in results["matches"]:
            metadata = res["metadata"]
            text = metadata.pop(self._text_key)
            docs.append(Document(page_content=text, metadata=metadata))
        return docs

    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        embedding: Embeddings,
        metadatas: Optional[List[dict]] = None,
        batch_size: int = 32,
        text_key: str = "text",
        index_name: Optional[str] = None,
        namespace: Optional[str] = None,
        **kwargs: Any,
    ) -> Pinecone:
        """Construct Pinecone wrapper from raw documents.

        This is a user friendly interface that:
            1. Embeds documents.
            2. Adds the documents to a provided Pinecone index

        This is intended to be a quick way to get started.

        Example:
            .. code-block:: python

                from langchain import Pinecone
                from langchain.embeddings import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings()
                pinecone = Pinecone.from_texts(
                    texts,
                    embeddings,
                    index_name="langchain-demo"
                )
        """
        try:
            import pinecone
        except ImportError:
            raise ValueError(
                "Could not import pinecone python package. "
                "Please install it with `pip install pinecone-client`."
            )
        _index_name = index_name or str(uuid.uuid4())
        indexes = pinecone.list_indexes()  # checks if provided index exists
        if _index_name in indexes:
            index = pinecone.Index(_index_name)
        else:
            index = None
        for i in range(0, len(texts), batch_size):
            # set end position of batch
            i_end = min(i + batch_size, len(texts))
            # get batch of texts and ids
            lines_batch = texts[i : i + batch_size]
            ids_batch = [str(uuid.uuid4()) for n in range(i, i_end)]
            # create embeddings
            embeds = embedding.embed_documents(lines_batch)
            # prep metadata and upsert batch
            if metadatas:
                metadata = metadatas[i : i + batch_size]
            else:
                metadata = [{} for _ in range(i, i_end)]
            for j, line in enumerate(lines_batch):
                metadata[j][text_key] = line
            to_upsert = zip(ids_batch, embeds, metadata)
            # Create index if it does not exist
            if index is None:
                pinecone.create_index(_index_name, dimension=len(embeds[0]))
                index = pinecone.Index(_index_name)
            # upsert to Pinecone
            index.upsert(vectors=list(to_upsert), namespace=namespace)
        return cls(index, embedding.embed_query, text_key)

    @classmethod
    def from_existing_index(
        cls, index_name: str, embedding: Embeddings, text_key: str = "text"
    ) -> Pinecone:
        """Load pinecone vectorstore from index name."""
        try:
            import pinecone
        except ImportError:
            raise ValueError(
                "Could not import pinecone python package. "
                "Please install it with `pip install pinecone-client`."
            )

        return cls(pinecone.Index(index_name), embedding.embed_query, text_key)
