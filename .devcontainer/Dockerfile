FROM mcr.microsoft.com/devcontainers/miniconda:1-3

# Use conda directory
ENV CONDA_DIR=/opt/conda
ENV PATH="$CONDA_DIR/bin:$PATH"

# Create 'bera' environment with mamba and strict channel priority
RUN conda init bash
RUN conda install mamba -c conda-forge -y
RUN conda create -n bera -c conda-forge -c appliedgrg python=3.11 mamba --override-channels -y 

# Copy requirements and install via mamba
COPY conda_requirements.txt /tmp/conda_requirements.txt
RUN conda config --set channel_priority strict
RUN mamba install -n bera -c conda-forge -c appliedgrg --file /tmp/conda_requirements.txt -y 
RUN rm /tmp/conda_requirements.txt

# Automatically activate the 'bera' environment in new shells
RUN echo "conda activate bera" >> ~/.bashrc

# Use bash as default shell (to ensure conda activation)
SHELL ["bash", "-lc"]

# [Optional] Uncomment to install a different version of Python than the default
# RUN conda install -y python=3.6 \
#     && pip install --no-cache-dir pipx \
#     && pipx reinstall-all

# [Optional] Uncomment this section to install additional OS packages.
# RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
#     && apt-get -y install --no-install-recommends <your-package-list-here>
