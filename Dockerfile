# 1. Start from a standard, stable Node.js Debian server
FROM node:20-bookworm

USER root

# 2. Install Python and the compilers needed for Data Science
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. Create a Virtual Environment for Python
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. Install your teammate's specific Data Science libraries
RUN pip install --no-cache-dir \
    flask \
    pandas \
    pypdf \
    jieba \
    beautifulsoup4 \
    wordcloud \
    matplotlib \
    scikit-learn \
    sentence-transformers

# 5. Install the latest version of n8n globally
RUN npm install -g n8n

# 6. Ensure n8n is accessible outside the container
ENV N8N_HOST=0.0.0.0

# 7. Switch to the 'node' user so n8n connects to your existing ~/.n8n volume
USER node
WORKDIR /home/node

# 8. Start n8n when the container boots!
CMD ["n8n"]
