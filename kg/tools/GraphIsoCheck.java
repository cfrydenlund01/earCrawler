import org.apache.jena.rdf.model.Model;
import org.apache.jena.rdf.model.ModelFactory;
import org.apache.jena.riot.RDFDataMgr;

public class GraphIsoCheck {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: GraphIsoCheck <file1> <file2>");
            System.exit(2);
        }
        Model m1 = ModelFactory.createDefaultModel();
        Model m2 = ModelFactory.createDefaultModel();
        RDFDataMgr.read(m1, args[0]);
        RDFDataMgr.read(m2, args[1]);
        if (m1.isIsomorphicWith(m2)) {
            System.exit(0);
        } else {
            System.err.println("Graphs not isomorphic");
            System.exit(1);
        }
    }
}
