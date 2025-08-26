import java.io.FileInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Paths;

import org.apache.jena.ontology.OntModel;
import org.apache.jena.ontology.OntModelSpec;
import org.apache.jena.rdf.model.Model;
import org.apache.jena.rdf.model.ModelFactory;
import org.apache.jena.query.*;

public class OwlAsk {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: OwlAsk query.rq data1.ttl [data2.ttl ...]");
            System.exit(1);
        }
        String queryFile = args[0];
        Model base = ModelFactory.createDefaultModel();
        for (int i = 1; i < args.length; i++) {
            try (InputStream in = new FileInputStream(args[i])) {
                base.read(in, null, "TTL");
            }
        }
        OntModel model = ModelFactory.createOntologyModel(OntModelSpec.OWL_MEM_MICRO_RULE_INF, base);
        String queryString = new String(Files.readAllBytes(Paths.get(queryFile)), java.nio.charset.StandardCharsets.UTF_8);
        Query query = QueryFactory.create(queryString);
        try (QueryExecution qexec = QueryExecutionFactory.create(query, model)) {
            boolean result = qexec.execAsk();
            String out = "{\"query\":\"" + queryFile.replace("\\", "\\\\").replace("\"", "\\\"") + "\",\"result\":" + result + "}";
            System.out.println(out);
            System.exit(result ? 0 : 1);
        }
    }
}
