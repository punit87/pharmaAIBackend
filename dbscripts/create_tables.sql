CREATE TABLE documents (
    id integer NOT NULL,
    name text NOT NULL,
    CONSTRAINT documents_pkey PRIMARY KEY (id),
    CONSTRAINT documents_name_key UNIQUE (name)
);

CREATE TABLE source_files (
    id integer NOT NULL,
    document_id integer NOT NULL,
    file_name text NOT NULL,
    file_type text NOT NULL,
    CONSTRAINT source_files_pkey PRIMARY KEY (id),
    CONSTRAINT source_files_document_id_file_name_key UNIQUE (document_id, file_name),
    CONSTRAINT source_files_file_type_check CHECK (file_type IN ('docx', 'pdf', 'other')),
    CONSTRAINT source_files_document_id_fkey FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE batch_runs (
    id integer NOT NULL,
    run_number integer NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    processed_files integer DEFAULT 0,
    batch_status text DEFAULT 'NOT_STARTED'::text NOT NULL,
    CONSTRAINT batch_runs_pkey PRIMARY KEY (id),
    CONSTRAINT batch_runs_run_number_key UNIQUE (run_number),
    CONSTRAINT batch_runs_batch_status_check CHECK (batch_status IN ('SUCCESS', 'FAILED', 'RUNNING', 'TERMINATED', 'NOT_STARTED'))
);

CREATE TABLE source_file_runs (
    id integer NOT NULL,
    source_file_id integer NOT NULL,
    batch_run_id integer NOT NULL,
    author text,
    created_dt date,
    last_modified_dt date,
    number_pages integer,
    CONSTRAINT source_file_runs_pkey PRIMARY KEY (id),
    CONSTRAINT source_file_runs_source_file_id_batch_run_id_key UNIQUE (source_file_id, batch_run_id),
    CONSTRAINT source_file_runs_number_pages_check CHECK (number_pages > 0),
    CONSTRAINT source_file_runs_source_file_id_fkey FOREIGN KEY (source_file_id) REFERENCES source_files(id) ON DELETE CASCADE,
    CONSTRAINT source_file_runs_batch_run_id_fkey FOREIGN KEY (batch_run_id) REFERENCES batch_runs(id) ON DELETE CASCADE
);

CREATE TABLE sections (
    id integer NOT NULL,
    section_name text NOT NULL,
    CONSTRAINT sections_pkey PRIMARY KEY (id),
    CONSTRAINT sections_section_name_key UNIQUE (section_name)
);

CREATE TABLE source_file_run_sections (
    source_file_run_id integer NOT NULL,
    section_id integer NOT NULL,
    CONSTRAINT source_file_run_sections_pkey PRIMARY KEY (source_file_run_id, section_id),
    CONSTRAINT source_file_run_sections_source_file_run_id_fkey FOREIGN KEY (source_file_run_id) REFERENCES source_file_runs(id) ON DELETE CASCADE,
    CONSTRAINT source_file_run_sections_section_id_fkey FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE CASCADE
);

CREATE TABLE content_blocks (
    id integer NOT NULL,
    source_file_run_id integer NOT NULL,
    section_id integer,
    block_number integer NOT NULL,
    content_type text,
    content text,
    coord_x1 integer,
    coord_y1 integer,
    coord_x2 integer,
    coord_y2 integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    faiss_index_id integer,
    CONSTRAINT content_blocks_pkey PRIMARY KEY (id),
    CONSTRAINT content_blocks_source_file_run_id_block_number_key UNIQUE (source_file_run_id, block_number),
    CONSTRAINT content_blocks_content_type_check CHECK (content_type IN ('text', 'image', 'table', 'figure', 'title', 'list')),
    CONSTRAINT content_blocks_source_file_run_id_fkey FOREIGN KEY (source_file_run_id) REFERENCES source_file_runs(id) ON DELETE CASCADE,
    CONSTRAINT content_blocks_section_id_fkey FOREIGN KEY (section_id) REFERENCES sections(id) ON DELETE SET NULL
);

CREATE TABLE skipped_block_items (
    id integer NOT NULL,
    batch_run_id integer NOT NULL,
    parent_block_type character varying(20) NOT NULL,
    skipped_block_type character varying(20) NOT NULL,
    section_name character varying(255),
    parent_block_content character varying(1000),
    skipped_block_content character varying(1000),
    parent_block_coordinates integer[],
    skipped_block_coordinates integer[],
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT skipped_block_items_pkey PRIMARY KEY (id),
    CONSTRAINT skipped_block_items_batch_run_id_fkey FOREIGN KEY (batch_run_id) REFERENCES batch_runs(id) ON DELETE CASCADE
);